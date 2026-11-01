"""Home tab: Operations Dashboard backed by stored data (M44, redesigned in M53).

English-only and strictly left-to-right (the dashboard never switches to RTL,
whatever the rest of the application does).  All figures come from
``core.operations_dashboard``:

* :func:`build_snapshot` - KPIs (with definition, unit, source, freshness and
  drill-down), portfolio rows, alerts and recent activity for the current
  :class:`DashboardFilter`;
* :func:`build_well_detail` - chart series and the trajectory preview of the
  selected well.

Nothing is simulated: a value that cannot be computed shows "No data" plus the
reason, a chart without stored data paints "Unavailable" with the reason, and
a failed load shows the error type while keeping the previous figures marked
as stale.

Loading runs in ``ReadOnlyQueryWorker`` with its own read-only SQLite
connection when the database is a file; in-memory databases (tests) are read
synchronously.  A refresh requested while a load is running is queued, never
run concurrently, and a result whose filter (or selected well) no longer
matches the current one is discarded as stale.

Double-clicking a well, a report, an alert or an activity item navigates
through ``navigate_requested`` with the same payloads as the hierarchy tree;
clicking a KPI card drills down (filters the portfolio or opens the tab).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.base_tab import DrillTabBase
from tabs.dashboard_widgets import (
    DARK, THEMES, KpiCard, MiniChart, Panel, TrajectoryPreview, format_number, severity_color, stylesheet,
)

logger = logging.getLogger(__name__)

SURVEY_LABELS = {"READY": "OK", "REVIEW_REQUIRED": "Review", "INSUFFICIENT_DATA": "Insufficient",
                 "NO_DATA": "None", "ERROR": "Error"}
WELL_COLUMNS = ("Well", "Company / Project", "Type", "Status", "Rig", "Reports", "Latest report", "Depth (m)",
                "Target (m)", "Days since", "Survey MD / TVD (m)", "Survey", "Attention")
MONEY_KPIS = {"cost_actual", "cost_per_metre", "npt_cost"}
STATUS_CHOICES = (("All statuses", None), ("Active", "active"), ("Planning", "planning"),
                  ("Completed", "completed"), ("Other", "other"))
CHARTS = (
    ("depth", "Depth vs time"), ("rop", "ROP"), ("npt_cat", "NPT by category"), ("npt_trend", "NPT trend"),
    ("mw", "Mud weight"), ("bits", "Bit runs: footage"), ("mse", "MSE (saved calculations)"),
    ("cost", "Cost vs AFE by category"),
)
SELECT_WELL = "Select a well in the portfolio"


def format_kpi_value(kpi) -> str:
    """Display text of a KPI; None is always "No data", never 0."""
    if kpi.value is None:
        return "No data"
    if isinstance(kpi.value, date):
        return kpi.value.isoformat()
    if isinstance(kpi.value, float):
        text = f"{kpi.value:,.2f}" if kpi.key in MONEY_KPIS else f"{kpi.value:,.1f}"
    else:
        text = f"{kpi.value:,}"
    return f"{text} {kpi.unit}".strip()


class HomeTab(DrillTabBase):
    """Operations dashboard."""

    navigate_requested = Signal(dict)

    def __init__(self, db_manager, parent=None):
        super().__init__("HomeTab", db_manager, parent)
        from core.operations_dashboard import DashboardFilter
        self.db = db_manager
        self.db_manager = db_manager
        self.parent_window = parent           # MainWindow (backup service, autosave, tabs)
        self.parent_tab_widget = None
        self.status_manager.register_widget("HomeTab", self)
        self.snapshot = None
        self.detail = None
        self.filters = DashboardFilter()
        self.focus_well_id: Optional[int] = None
        self.theme = DARK
        self.last_update: Optional[datetime] = None
        self.backup_info = None
        self._worker = None
        self._refresh_pending = False
        self._detail_worker = None
        self._detail_pending = False
        self._populating = False
        self.load_count = 0
        self.stale_discarded = 0
        self.today_provider = date.today       # the dashboard's "today" (tests, screenshots)
        self.init_ui()
        # First load on the next event-loop turn, once the main window is built.
        QTimer.singleShot(0, self.load_data)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_data)
        self.refresh_timer.start(300_000)     # every 5 minutes

    # ------------------------------------------------------------------ UI
    def init_ui(self):
        self.setObjectName("dashboardRoot")
        self.setLayoutDirection(Qt.LeftToRight)       # English-only dashboard, never RTL
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        canvas = QWidget()
        canvas.setObjectName("dashboardCanvas")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())
        layout.addWidget(self._build_filter_bar())
        layout.addWidget(self._build_kpis())

        self.empty_panel = Panel("No wells in scope")
        self.empty_text = QLabel("Create a well, or import a daily drilling report, to populate the dashboard.")
        self.empty_text.setObjectName("muted")
        self.empty_text.setWordWrap(True)
        self.empty_panel.body().addWidget(self.empty_text)
        empty_buttons = QHBoxLayout()
        for text, slot in (("New well", self.open_new_well_tab), ("Import DDR", self.import_ddr),
                           ("Reset filters", self.reset_filters)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            empty_buttons.addWidget(button)
        empty_buttons.addStretch()
        self.empty_panel.body().addLayout(empty_buttons)
        self.empty_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.empty_panel.setVisible(False)
        layout.addWidget(self.empty_panel)

        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(self._build_portfolio(), 3)
        content_layout.addWidget(self._section_title("CHARTS"))
        content_layout.addWidget(self._build_charts())
        content_layout.addLayout(self._build_bottom_row())
        layout.addWidget(self.content, 100)

        quick = QHBoxLayout()
        for text, slot in (("New daily report", self.new_report), ("Import DDR", self.import_ddr),
                           ("New well", self.open_new_well_tab), ("Export Center", self.export_data),
                           ("Analysis", self.open_analysis_tab)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            quick.addWidget(button)
        quick.addStretch()
        layout.addLayout(quick)
        layout.addStretch(1)              # spare height (empty state) collects here, not in the filter bar

        scroll.setWidget(canvas)
        outer.addWidget(scroll)
        self.apply_theme("dark")

    @staticmethod
    def _section_title(text):
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _build_header(self):
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Operations Dashboard")
        title.setObjectName("dashTitle")
        self.scope_label = QLabel("All wells · last 7 days")
        self.scope_label.setObjectName("dashSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.scope_label)
        header.addLayout(titles)
        header.addStretch()
        self.state_label = QLabel("Loading…")
        self.state_label.setObjectName("dashState")
        header.addWidget(self.state_label)
        self.theme_btn = QPushButton("Light theme")
        self.theme_btn.setToolTip("Switch between the dark and the light dashboard theme")
        self.theme_btn.clicked.connect(lambda: self.apply_theme("light" if self.theme is DARK else "dark"))
        header.addWidget(self.theme_btn)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.clicked.connect(self.load_data)
        header.addWidget(self.refresh_btn)
        return header

    def _build_filter_bar(self):
        bar = QFrame()
        bar.setObjectName("filterBar")
        bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        self.filter_combos = {}
        for key, label in (("company", "Company"), ("project", "Project"), ("well", "Well"), ("rig", "Rig"),
                           ("status", "Status"), ("period", "Period")):
            caption = QLabel(label)
            caption.setObjectName("muted")
            combo = QComboBox()
            combo.setObjectName(f"filter_{key}")
            layout.addWidget(caption)
            layout.addWidget(combo)
            self.filter_combos[key] = combo
        for text, value in STATUS_CHOICES:
            self.filter_combos["status"].addItem(text, value)
        from core.operations_dashboard import PERIODS
        for _key, text, days in PERIODS:
            self.filter_combos["period"].addItem(text, days)
        for key in ("company", "project", "well", "rig"):
            self.filter_combos[key].addItem(f"All {key}s" if key != "company" else "All companies", None)
        for combo in self.filter_combos.values():
            combo.currentIndexChanged.connect(self._filters_changed)
        layout.addStretch()
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self.reset_filters)
        layout.addWidget(self.reset_btn)
        return bar

    def _build_kpis(self):
        from core.operations_dashboard import KPI_GROUPS
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.kpi_grid = grid
        self.kpi_cards = {}
        row = 0
        for group, keys in KPI_GROUPS:
            grid.addWidget(self._section_title(group.upper()), row, 0, 1, 5)
            row += 1
            for column, key in enumerate(keys):
                card = KpiCard()
                card.clicked.connect(self.drill_down)
                self.kpi_cards[key] = card
                grid.addWidget(card, row, column)
            row += 1
        for column in range(5):
            grid.setColumnStretch(column, 1)
        return box

    def _build_portfolio(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        wells_box = Panel("Well portfolio")
        self.portfolio_panel = wells_box
        self.wells_table = QTableWidget(0, len(WELL_COLUMNS))
        self.wells_table.setHorizontalHeaderLabels(WELL_COLUMNS)
        self.wells_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.wells_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wells_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.wells_table.setAlternatingRowColors(True)
        self.wells_table.setShowGrid(False)
        self.wells_table.setMinimumHeight(220)
        self.wells_table.verticalHeader().setVisible(False)
        self.wells_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.wells_table.horizontalHeader().setStretchLastSection(True)
        # Snapshot order (needs-attention first) until the user sorts by a column.
        self.wells_table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.wells_table.cellDoubleClicked.connect(lambda row, _column: self.open_selected_well())
        wells_box.body().addWidget(self.wells_table)
        actions = QHBoxLayout()
        self.open_well_btn = QPushButton("Open well")
        self.open_report_btn = QPushButton("Open latest report")
        self.open_trajectory_btn = QPushButton("Open trajectory")
        self.open_well_btn.clicked.connect(self.open_selected_well)
        self.open_report_btn.clicked.connect(self.open_selected_latest_report)
        self.open_trajectory_btn.clicked.connect(self.open_selected_trajectory)
        for button in (self.open_well_btn, self.open_report_btn, self.open_trajectory_btn):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        hint = QLabel("Select a row for its charts; double-click to open the well.")
        hint.setObjectName("muted")
        actions.addWidget(hint)
        wells_box.body().addLayout(actions)
        self.wells_table.itemSelectionChanged.connect(self._selection_changed)
        splitter.addWidget(wells_box)

        selected = Panel("Selected well")
        self.selected_panel = selected
        self.selected_title = QLabel(SELECT_WELL)
        self.selected_title.setObjectName("panelTitle")
        selected.body().addWidget(self.selected_title)
        facts = QGridLayout()
        facts.setHorizontalSpacing(14)
        facts.setVerticalSpacing(3)
        facts.setColumnStretch(1, 1)
        self.selected_facts = {}
        for index, key in enumerate(("Company / project", "Rig", "Type / status", "Latest report", "Depth / target",
                                     "Survey", "Closure", "Attention")):
            caption = QLabel(key)
            caption.setObjectName("muted")
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            facts.addWidget(caption, index, 0, Qt.AlignTop)
            facts.addWidget(value, index, 1)
            self.selected_facts[key] = value
        selected.body().addLayout(facts)
        trajectory_title = QLabel("Trajectory preview (stored surveys, minimum curvature)")
        trajectory_title.setObjectName("muted")
        selected.body().addWidget(trajectory_title)
        self.trajectory_preview = TrajectoryPreview()
        selected.body().addWidget(self.trajectory_preview, 1)
        buttons = QHBoxLayout()
        self.full_trajectory_btn = QPushButton("Open full trajectory view")
        self.full_trajectory_btn.clicked.connect(self.open_selected_trajectory)
        self.full_trajectory_btn.setEnabled(False)
        self.clear_selection_btn = QPushButton("Clear selection")
        self.clear_selection_btn.clicked.connect(self.clear_focus)
        buttons.addWidget(self.full_trajectory_btn)
        buttons.addWidget(self.clear_selection_btn)
        buttons.addStretch()
        selected.body().addLayout(buttons)
        splitter.addWidget(selected)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.portfolio_splitter = splitter
        return splitter

    def _build_charts(self):
        box = QWidget()
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        self.charts = {}
        self.chart_panels = {}
        for index, (key, title) in enumerate(CHARTS):
            panel = Panel(title)
            chart = MiniChart(title)
            panel.body().addWidget(chart, 1)
            self.charts[key] = chart
            self.chart_panels[key] = panel
            grid.addWidget(panel, index // 4, index % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        self.ecd_note = QLabel("ECD: no ECD values are stored in the database, so no ECD chart is shown.")
        self.ecd_note.setObjectName("muted")
        grid.addWidget(self.ecd_note, 2, 0, 1, 4)
        return box

    def _build_bottom_row(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        attention_box = Panel("Alerts")
        self.attention_list = QListWidget()
        self.attention_list.setWordWrap(True)
        self.attention_list.setMinimumHeight(180)
        self.attention_list.itemDoubleClicked.connect(self._attention_activated)
        attention_box.body().addWidget(self.attention_list)
        row.addWidget(attention_box, 3)

        recent_box = Panel("Recent activity")
        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels(("Date", "Well", "#", "Depth (m)", "Status"))
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setShowGrid(False)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.cellDoubleClicked.connect(self._recent_activated)
        self.recent_table.setMinimumHeight(130)
        caption = QLabel("Daily reports")
        caption.setObjectName("muted")
        recent_box.body().addWidget(caption)
        recent_box.body().addWidget(self.recent_table)
        caption = QLabel("Imports and saved calculations")
        caption.setObjectName("muted")
        recent_box.body().addWidget(caption)
        self.activity_list = QListWidget()
        self.activity_list.setMinimumHeight(90)
        self.activity_list.itemDoubleClicked.connect(self._activity_activated)
        recent_box.body().addWidget(self.activity_list)
        row.addWidget(recent_box, 3)

        system_box = Panel("System")
        system_layout = QGridLayout()
        self.system_labels = {}
        for index, key in enumerate(("Database", "Last verified backup", "Autosave")):
            caption = QLabel(key)
            caption.setObjectName("muted")
            system_layout.addWidget(caption, index, 0)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            system_layout.addWidget(value, index, 1)
            self.system_labels[key] = value
        system_box.body().addLayout(system_layout)
        system_box.body().addStretch()
        row.addWidget(system_box, 2)
        return row

    # --------------------------------------------------------------- theme
    def apply_theme(self, name: str):
        self.theme = THEMES[name]
        self.setStyleSheet(stylesheet(self.theme))
        self.theme_btn.setText("Light theme" if name == "dark" else "Dark theme")
        for chart in self.charts.values():
            chart.set_theme(self.theme)
        self.trajectory_preview.set_theme(self.theme)
        if self.snapshot is not None:
            self._fill_kpis(self.snapshot)
            self._fill_wells(self.snapshot)
            self._fill_attention(self.snapshot)
            self._fill_activity(self.snapshot)
            self._fill_charts()

    # ------------------------------------------------------------- filters
    def current_filters(self):
        from core.operations_dashboard import DashboardFilter
        combos = self.filter_combos
        return DashboardFilter(company=combos["company"].currentData(), project=combos["project"].currentData(),
                               well_id=combos["well"].currentData(), rig=combos["rig"].currentData(),
                               status_group=combos["status"].currentData(),
                               period_days=combos["period"].currentData())

    def _filters_changed(self, *_args):
        if self._populating:
            return
        self.filters = self.current_filters()
        if self.filters.well_id:
            self.focus_well_id = self.filters.well_id
        self.load_data()

    def set_filter(self, **values):
        """Programmatic filter change (KPI drill-down, tests): keys company, project, well_id, rig,
        status_group, period_days."""
        names = {"company": "company", "project": "project", "well_id": "well", "rig": "rig",
                 "status_group": "status", "period_days": "period"}
        self._populating = True
        try:
            for key, value in values.items():
                combo = self.filter_combos[names[key]]
                index = combo.findData(value)
                if index < 0 and value is not None:
                    combo.addItem(str(value), value)
                    index = combo.count() - 1
                combo.setCurrentIndex(max(0, index))
        finally:
            self._populating = False
        self._filters_changed()

    def reset_filters(self):
        from core.operations_dashboard import WINDOW_DAYS
        self.set_filter(company=None, project=None, well_id=None, rig=None, status_group=None,
                        period_days=WINDOW_DAYS)

    def _populate_filter_options(self, options):
        self._populating = True
        try:
            for key, values in (("company", options.get("companies", [])), ("project", options.get("projects", [])),
                                ("rig", options.get("rigs", [])),
                                ("well", options.get("wells", []))):
                combo = self.filter_combos[key]
                current = combo.currentData()
                while combo.count() > 1:
                    combo.removeItem(1)
                for value in values:
                    if key == "well":
                        combo.addItem(value[1], value[0])
                    else:
                        combo.addItem(value, value)
                index = combo.findData(current)
                combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._populating = False

    # -------------------------------------------------------------- loading
    def _snapshot_job(self):
        backup_service = getattr(self.parent_window, "backup_service", None)
        today = self.today_provider()
        filters = self.filters

        def job(db):
            from core.operations_dashboard import build_snapshot
            snapshot = build_snapshot(db, today=today, filters=filters)
            backup = None
            if backup_service is not None:
                try:
                    found = backup_service.list_backups(deep=False)
                    backup = ("found", found[0][1].get("created_utc")) if found else ("none", None)
                except OSError as exc:
                    backup = ("unavailable", type(exc).__name__)
            return filters, snapshot, backup
        return job

    def _start(self, job, on_done, on_failed, on_finished):
        """Run ``job(db)`` in a read-only worker (file DB) or inline; returns the worker or None."""
        from core.export_jobs import has_isolated_reader
        if has_isolated_reader(self.db):
            from core.async_workers import ReadOnlyQueryWorker
            worker = ReadOnlyQueryWorker(self.db, job, self)
            worker.completed.connect(on_done)
            worker.failed.connect(on_failed)
            worker.finished.connect(on_finished)
            worker.start()
            return worker
        try:
            result = job(self.db)
        except Exception as exc:
            logger.warning("Dashboard load failed: %s", type(exc).__name__)
            on_failed(type(exc).__name__)
        else:
            on_done(result)
        return None

    def load_data(self):
        """Reload the dashboard; queued if a load is already running."""
        if self.db is None:
            return
        if self._worker is not None:
            self._refresh_pending = True
            return
        self.state_label.setText("Loading…")
        self.refresh_btn.setEnabled(False)
        self._worker = self._start(self._snapshot_job(), self._on_loaded, self._on_failed, self._on_worker_finished)
        if self._worker is None:
            self.refresh_btn.setEnabled(True)

    def _on_worker_finished(self):
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self.refresh_btn.setEnabled(True)
        if self._refresh_pending:
            self._refresh_pending = False
            self.load_data()

    def wait_for_load(self, timeout_ms: int = 10_000) -> bool:
        """Block until running loads finish (tests and shutdown)."""
        finished = True
        for worker in (self._worker, self._detail_worker):
            if worker is not None:
                finished = worker.wait(timeout_ms) and finished
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        return finished

    def _on_failed(self, error_type: str):
        stale = f" — showing data from {self.last_update:%H:%M:%S}" if self.last_update else ""
        self.state_label.setText(f"Load failed ({error_type}){stale}")
        self.state_label.setStyleSheet(f"color: {self.theme['red']};")

    def _on_loaded(self, result):
        if len(result) == 3:
            filters, snapshot, backup = result
        else:                                  # (snapshot, backup) from older callers
            (snapshot, backup), filters = result, self.filters
        if filters != self.filters:
            # The filter changed while this load ran; the queued reload brings the current scope.
            self.stale_discarded += 1
            self._refresh_pending = True
            return
        self.snapshot, self.backup_info = snapshot, backup
        self.last_update = datetime.now()
        self.load_count += 1
        self.state_label.setStyleSheet("")
        self.state_label.setText(f"Updated {self.last_update:%H:%M:%S} · data as of {snapshot.today.isoformat()}")
        self._populate_filter_options(getattr(snapshot, "options", {}))
        self.scope_label.setText(self._scope_text(snapshot))
        self._fill_kpis(snapshot)
        self.empty_panel.setVisible(snapshot.empty)
        self.content.setVisible(not snapshot.empty)
        if snapshot.empty:
            filtered = filters != type(filters)()
            self.empty_panel.title.setText("No wells match the filters" if filtered else "No wells yet")
            self.empty_text.setText("Change or reset the filters to see wells." if filtered else
                                    "Create a well, or import a daily drilling report, to populate the dashboard.")
        if self.focus_well_id is not None and not any(w.well_id == self.focus_well_id for w in snapshot.wells):
            self.focus_well_id = None
        if self.focus_well_id is None and len(snapshot.wells) == 1 and filters.well_id:
            self.focus_well_id = snapshot.wells[0].well_id
        self._fill_wells(snapshot)
        self._fill_attention(snapshot)
        self._fill_recent(snapshot)
        self._fill_activity(snapshot)
        self._fill_system(backup)
        self._load_detail()

    @staticmethod
    def _scope_text(snapshot) -> str:
        f = snapshot.filters
        parts = [f.company or "All companies", f.project or "all projects"]
        if f.well_id:
            parts.append(next((w.name for w in snapshot.wells if w.well_id == f.well_id), "well"))
        if f.rig:
            parts.append(f"rig {f.rig}")
        if f.status_group:
            parts.append(f.status_group)
        period = "all dates" if f.period_days is None else f"last {f.period_days} days"
        return " · ".join(parts) + f" · {period} · {len(snapshot.wells)} well(s)"

    # ---------------------------------------------------------- well detail
    def _load_detail(self):
        well_id = self.focus_well_id
        if well_id is None:
            self.detail = None
            self._fill_selected()
            self._fill_charts()
            return
        if self._detail_worker is not None:
            self._detail_pending = True
            return

        def job(db):
            from core.operations_dashboard import build_well_detail
            return well_id, build_well_detail(db, well_id)
        self._detail_worker = self._start(job, self._on_detail_loaded, self._on_detail_failed,
                                          self._on_detail_finished)

    def _on_detail_loaded(self, result):
        well_id, detail = result
        if well_id != self.focus_well_id:
            self.stale_discarded += 1          # selection moved on; the queued load brings the new well
            self._detail_pending = True
            return
        self.detail = detail
        self._fill_selected()
        self._fill_charts()

    def _on_detail_failed(self, error_type: str):
        self.detail = None
        self.selected_title.setText(f"Could not load the selected well ({error_type})")
        self._fill_charts(error=f"Load failed ({error_type})")

    def _on_detail_finished(self):
        worker, self._detail_worker = self._detail_worker, None
        if worker is not None:
            worker.deleteLater()
        if self._detail_pending:
            self._detail_pending = False
            self._load_detail()

    def _selection_changed(self):
        self._update_well_actions()
        well = self._selected_well()
        if well is not None and well.well_id != self.focus_well_id:
            self.focus_well_id = well.well_id
            self._load_detail()

    def clear_focus(self):
        self.wells_table.clearSelection()
        if self.filters.well_id:
            self.set_filter(well_id=None)
            return
        self.focus_well_id = None
        self._load_detail()

    # -------------------------------------------------------------- filling
    @staticmethod
    def _item(text, align_right=False, payload=None, color=None):
        item = QTableWidgetItem(text)
        if align_right:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if payload is not None:
            item.setData(Qt.UserRole, payload)
        if color:
            item.setForeground(QColor(color))
        return item

    def _fill_kpis(self, snapshot):
        for key, card in self.kpi_cards.items():
            if key in snapshot.kpis:
                card.set_kpi(snapshot.kpis[key], self.theme)

    def _fill_wells(self, snapshot):
        t = self.theme
        table = self.wells_table
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(len(snapshot.wells))
        focus_row = None
        for row, well in enumerate(snapshot.wells):
            latest = "—"
            if well.latest_report_date is not None:
                latest = f"#{well.latest_report_number} · {well.latest_report_date.isoformat()}"
            depth = "not reported" if well.report_count and well.latest_depth is None else (
                "—" if well.latest_depth is None else f"{well.latest_depth:,.1f}")
            survey = "—" if well.survey_md is None else f"{well.survey_md:,.1f} / {well.survey_tvd:,.1f}"
            worst = well.worst_severity
            attention = "; ".join(f.message for f in well.flags) or "OK"
            values = (
                self._item(well.name, payload=well.well_id),
                self._item(f"{well.company} / {well.project}"),
                self._item(well.well_type or "—"),
                self._item(well.status),
                self._item(getattr(well, "rig", "—")),
                self._item(str(well.report_count), True),
                self._item(latest),
                self._item(depth, True, color=t["amber"] if depth == "not reported" else None),
                self._item(format_number(getattr(well, "target_depth", None)), True),
                self._item("—" if well.days_since_report is None else str(well.days_since_report), True),
                self._item(survey, True),
                self._item(SURVEY_LABELS.get(well.survey_status, well.survey_status),
                           color=t["amber"] if well.survey_status == "REVIEW_REQUIRED" else None),
                self._item(attention, color=severity_color(t, worst)),
            )
            for column, item in enumerate(values):
                table.setItem(row, column, item)
            if well.well_id == self.focus_well_id:
                focus_row = row
        table.setSortingEnabled(True)
        if focus_row is not None:
            table.selectRow(focus_row)
        else:
            table.clearSelection()
        table.blockSignals(False)
        self._update_well_actions()

    def _fill_attention(self, snapshot):
        self.attention_list.clear()
        if not snapshot.attention:
            item = QListWidgetItem("Nothing needs attention.")
            item.setForeground(QColor(self.theme["green"]))
            self.attention_list.addItem(item)
            return
        for flag in snapshot.attention:
            item = QListWidgetItem(f"{flag.severity.upper()} · {flag.well_name}: {flag.message}")
            item.setForeground(QColor(severity_color(self.theme, flag.severity)))
            item.setData(Qt.UserRole, flag)
            item.setToolTip(f"{flag.code} · double-click to open the {flag.target}")
            self.attention_list.addItem(item)

    def _fill_recent(self, snapshot):
        table = self.recent_table
        table.setSortingEnabled(False)
        table.setRowCount(len(snapshot.recent_reports))
        for row, report in enumerate(snapshot.recent_reports):
            depth = "not reported" if report["depth"] is None else f"{report['depth']:,.1f}"
            table.setItem(row, 0, self._item(report["date"].isoformat(), payload=report))
            table.setItem(row, 1, self._item(report["well_name"]))
            table.setItem(row, 2, self._item(str(report["number"]), True))
            table.setItem(row, 3, self._item(depth, True))
            table.setItem(row, 4, self._item(str(report["status"])))

    def _fill_activity(self, snapshot):
        self.activity_list.clear()
        entries = [a for a in getattr(snapshot, "activity", []) if a["kind"] != "report"]
        if not entries:
            item = QListWidgetItem("No document imports or saved calculations recorded.")
            item.setForeground(QColor(self.theme["muted"]))
            self.activity_list.addItem(item)
            return
        for entry in entries:
            item = QListWidgetItem(f"{entry['day'].isoformat()} · {entry['text']}")
            item.setData(Qt.UserRole, entry.get("payload"))
            self.activity_list.addItem(item)

    def _fill_selected(self):
        facts = self.selected_facts
        well = None
        if self.snapshot is not None and self.focus_well_id is not None:
            well = next((w for w in self.snapshot.wells if w.well_id == self.focus_well_id), None)
        detail = self.detail if self.detail is not None and self.detail.well_id == self.focus_well_id else None
        self.full_trajectory_btn.setEnabled(well is not None)
        if well is None:
            self.selected_title.setText(SELECT_WELL)
            for value in facts.values():
                value.setText("—")
            self.trajectory_preview.set_stations([], "Select a well to preview its trajectory")
            return
        self.selected_title.setText(well.name)
        facts["Company / project"].setText(f"{well.company} / {well.project}")
        facts["Rig"].setText(getattr(well, "rig", "—"))
        facts["Type / status"].setText(f"{well.well_type} · {well.status}")
        facts["Latest report"].setText(
            "None" if well.latest_report_date is None else
            f"#{well.latest_report_number} · {well.latest_report_date.isoformat()} "
            f"({well.days_since_report} d ago)")
        depth = "not reported" if well.latest_depth is None else f"{well.latest_depth:,.1f} m"
        target = getattr(well, "target_depth", None)
        facts["Depth / target"].setText(f"{depth} / " + ("not set" if target is None else f"{target:,.1f} m"))
        facts["Survey"].setText(f"{SURVEY_LABELS.get(well.survey_status, well.survey_status)} · "
                                f"{well.survey_stations} station(s)")
        closure = "—"
        if detail is not None and detail.closure is not None:
            closure = f"{detail.closure[0]:,.1f} m @ {detail.closure[1]:.1f}° (azimuth reference as stored)"
        facts["Closure"].setText(closure)
        facts["Attention"].setText("; ".join(f.message for f in well.flags) or "OK")
        if detail is None:
            self.trajectory_preview.set_stations([], "Loading…")
        else:
            reason = {"NO_DATA": "No survey stations stored for this well",
                      "INSUFFICIENT_DATA": "Fewer than two valid survey stations",
                      "ERROR": "Survey could not be composed"}.get(detail.trajectory_status, "")
            self.trajectory_preview.set_stations(detail.trajectory, reason)

    def _fill_charts(self, error: Optional[str] = None):
        snapshot, detail = self.snapshot, self.detail
        if detail is not None and detail.well_id != self.focus_well_id:
            detail = None
        charts = self.charts
        well_reason = error or (SELECT_WELL if detail is None else None)

        def well_series(key, kind, series, unit, reason, **kwargs):
            if well_reason:
                charts[key].set_data(kind, [], unit, unavailable=well_reason)
            else:
                charts[key].set_data(kind, series, unit, unavailable=reason, **kwargs)

        name = detail.name if detail else ""
        well_series("depth", "line", [(name, detail.depth_time, "cyan")] if detail else [], "Depth (m)",
                    "No reports with a 24:00 depth", invert_y=True)
        well_series("rop", "line", [(name, detail.rop, "teal")] if detail else [], "ROP (m/h)",
                    "No drilling-parameter ROP stored")
        well_series("mw", "line", [(name, detail.mud_weight, "blue")] if detail else [],
                    f"MW ({detail.mud_weight_unit if detail else 'pcf'}, as stored)", "No mud reports with MW")
        well_series("bits", "bar", [("Footage", [(b[0], b[1]) for b in detail.bit_runs], "amber")] if detail else [],
                    "Footage (m)", "No bit runs with valid depth in/out and hours")
        well_series("mse", "line", [(name, detail.mse, "cyan")] if detail else [], "MSE (psi)",
                    "No saved MSE calculations for this well")
        if detail and detail.cost_status not in ("single-currency", "no-records"):
            reason = {"multi-currency": "Cost records use several currencies; not combined",
                      "unknown-currency": "Cost records lack a currency; not combined"}[detail.cost_status]
            well_series("cost", "bar", [], "", reason)
        else:
            groups = detail.cost_groups if detail else []
            series = [("Planned (AFE)", [(g[0], g[1]) for g in groups if g[1] is not None], "blue"),
                      ("Actual", [(g[0], g[2]) for g in groups if g[2] is not None], "amber")]
            well_series("cost", "bar", series, f"Amount ({detail.cost_currency})" if detail and
                        detail.cost_currency else "Amount", "No cost records for this well")
        # NPT: the selected well (all dates) or the whole scope (selected period).
        if detail is not None:
            npt = list(detail.npt_by_category.items())
            charts["npt_cat"].set_data("hbar", [("NPT", npt, "multi")], f"NPT hours · {name} (all dates)",
                                       unavailable="No NPT time logged for this well")
        elif snapshot is not None:
            npt = list(getattr(snapshot, "npt_by_category", {}).items())
            charts["npt_cat"].set_data("hbar", [("NPT", npt, "multi")], "NPT hours · scope, selected period",
                                       unavailable="No NPT time logged in the selected period")
        daily = getattr(snapshot, "npt_daily", []) if snapshot is not None else []
        charts["npt_trend"].set_data("bar", [("NPT h", [(d, n) for d, n, _l in daily], "red")],
                                     "NPT hours per report day · scope",
                                     unavailable="No time logs in the selected period")

    def _fill_system(self, backup):
        # Describe the database the engine actually uses, not the configured path.
        engine = getattr(self.db, "engine", None)
        path = getattr(getattr(engine, "url", None), "database", None) or ""
        if path and path != ":memory:" and Path(path).is_file():
            size = Path(path).stat().st_size
            shown = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
            self.system_labels["Database"].setText(f"{Path(path).name} · {shown}")
        elif engine is not None and path in ("", ":memory:"):
            self.system_labels["Database"].setText("In-memory database")
        else:
            self.system_labels["Database"].setText("Unavailable")
        if backup is None:
            text = "Backup service not available"
        elif backup[0] == "none":
            text = "No verified backup found"
        elif backup[0] == "found":
            text = str(backup[1]).replace("T", " ") + " UTC"
        else:
            text = f"Could not read backups ({backup[1]})"
        self.system_labels["Last verified backup"].setText(text)
        managers = []
        if hasattr(self.parent_window, "_autosave_managers") and hasattr(self.parent_window, "auto_save_manager"):
            managers = self.parent_window._autosave_managers()
        active = sum(manager.active_timer_count() for manager in managers
                     if hasattr(manager, "active_timer_count"))
        self.system_labels["Autosave"].setText(
            f"{active} editor timer(s) running" if active else ("Paused" if managers else "Unknown"))

    # ------------------------------------------------------------ navigation
    def _selected_well(self):
        row = self.wells_table.currentRow()
        if row < 0 or self.snapshot is None or not self.wells_table.selectedItems():
            return None
        item = self.wells_table.item(row, 0)
        well_id = item.data(Qt.UserRole) if item else None
        return next((w for w in self.snapshot.wells if w.well_id == well_id), None)

    def _update_well_actions(self):
        well = self._selected_well()
        self.open_well_btn.setEnabled(well is not None)
        self.open_report_btn.setEnabled(bool(well and well.latest_report_id))
        self.open_trajectory_btn.setEnabled(well is not None)

    def _navigate(self, payload: dict):
        self.navigate_requested.emit(payload)

    def drill_down(self, kpi):
        """KPI card click: filter the portfolio, focus a list, or open the related tab."""
        target = kpi.drilldown or {}
        if "filter" in target:
            values = dict(status_group=None)
            values.update(target["filter"])
            self.set_filter(**values)
        elif "well" in target:
            self.focus_well(target["well"])
        elif target.get("alerts"):
            self.attention_list.setFocus()
        elif target.get("recent"):
            self.recent_table.setFocus()
        elif "tab" in target:
            self._navigate({"type": "well_tab", "well_id": self.focus_well_id, "tab_title": target["tab"]})

    def focus_well(self, well_id: int):
        """Select ``well_id`` in the portfolio (its charts and preview load)."""
        for row in range(self.wells_table.rowCount()):
            item = self.wells_table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == well_id:
                self.wells_table.selectRow(row)
                return True
        return False

    def open_selected_well(self):
        well = self._selected_well()
        if well:
            self._navigate({"type": "well", "id": well.well_id})

    def open_selected_latest_report(self):
        well = self._selected_well()
        if well and well.latest_report_id:
            self._navigate({"type": "daily_report", "id": well.latest_report_id, "report_id": well.latest_report_id,
                            "section_id": well.latest_report_section_id, "well_id": well.well_id})

    def open_selected_trajectory(self):
        well = self._selected_well()
        well_id = well.well_id if well else self.focus_well_id
        if well_id:
            self._navigate({"type": "well_tab", "well_id": well_id, "tab_title": "Trajectory",
                            "subtab": "viewer"})

    def _attention_activated(self, item):
        flag = item.data(Qt.UserRole)
        if flag is None:
            return
        if flag.target == "report" and flag.report_id:
            self._navigate({"type": "daily_report", "id": flag.report_id, "report_id": flag.report_id,
                            "section_id": flag.section_id, "well_id": flag.well_id})
        elif flag.target == "trajectory":
            self._navigate({"type": "well_tab", "well_id": flag.well_id, "tab_title": "Trajectory",
                            "subtab": "viewer"})
        elif flag.target == "npt":
            self._navigate({"type": "well_tab", "well_id": flag.well_id, "tab_title": "Analysis"})
        elif flag.target == "cost":
            self._navigate({"type": "well_tab", "well_id": flag.well_id, "tab_title": "Cost"})
        else:
            self._navigate({"type": "well", "id": flag.well_id})

    def _recent_activated(self, row, _column):
        item = self.recent_table.item(row, 0)
        report = item.data(Qt.UserRole) if item else None
        if report:
            self._navigate({"type": "daily_report", "id": report["report_id"], "report_id": report["report_id"],
                            "section_id": report["section_id"], "well_id": report["well_id"]})

    def _activity_activated(self, item):
        payload = item.data(Qt.UserRole)
        if payload:
            self._navigate(payload)

    # ---------------------------------------------------------- quick actions
    def _find_tab(self, text):
        tabs = getattr(self.parent_window, "tab_widget", None)
        if tabs is None:
            return None, None
        for index in range(tabs.count()):
            if text in tabs.tabText(index):
                return tabs, index
        return tabs, None

    def new_report(self):
        tabs, index = self._find_tab("Daily Report")
        if index is None:
            self.status_manager.show_error("HomeTab", "Daily Report tab not found")
            return
        tabs.setCurrentIndex(index)
        widget = tabs.widget(index)
        for name in ("new_report", "create_daily_report_for_current_section"):
            if hasattr(widget, name):
                getattr(widget, name)()
                break

    def import_ddr(self):
        if self.parent_window is not None and hasattr(self.parent_window, "open_excel_import"):
            self.parent_window.open_excel_import()

    def export_data(self):
        tabs, index = self._find_tab("Export")
        if index is not None:
            tabs.setCurrentIndex(index)

    def open_analysis_tab(self):
        tabs, index = self._find_tab("Analysis")
        if index is not None:
            tabs.setCurrentIndex(index)

    def open_new_well_tab(self):
        tabs, index = self._find_tab("Well Info")
        if index is None:
            return
        tabs.setCurrentIndex(index)
        widget = tabs.widget(index)
        if hasattr(widget, "create_new_well_dialog"):
            widget.create_new_well_dialog()

    # ------------------------------------------------------------ lifecycle
    def set_parent_tab_widget(self, tab_widget):
        self.parent_tab_widget = tab_widget

    def on_selection_changed(self, item_type, item_id):
        pass

    def on_well_changed(self, well_id, well_data):
        """The dashboard covers all wells; a selection change does not reload it."""

    def refresh(self):
        self.load_data()

    def cleanup(self):
        if hasattr(self, "refresh_timer"):
            self.refresh_timer.stop()
        self.wait_for_load()
