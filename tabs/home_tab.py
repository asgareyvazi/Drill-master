"""Home tab: operations dashboard backed by stored data (M44).

All figures come from ``core.operations_dashboard.build_snapshot``; each KPI
card's tooltip is its written definition.  Nothing is simulated: a value that
cannot be computed shows "No data", a failed load shows the error type and
keeps the previous figures marked as stale.

Loading runs in ``ReadOnlyQueryWorker`` with its own read-only SQLite
connection when the database is a file; in-memory databases (tests) share a
single connection and are read synchronously.  A refresh requested while a
load is running is queued, never run concurrently.

Double-clicking a well, a report or an attention item navigates through
``navigate_requested`` with the same payloads as the hierarchy tree.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.base_tab import DrillTabBase

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {"error": "#b42318", "warning": "#a15c07", "info": "#475467"}
STATE_COLORS = {"ok": "#1d6fb8", "warning": "#a15c07", "error": "#b42318", "no_data": "#98a2b3"}
SURVEY_LABELS = {"READY": "OK", "REVIEW_REQUIRED": "Review", "INSUFFICIENT_DATA": "Insufficient",
                 "NO_DATA": "None", "ERROR": "Error"}
WELL_COLUMNS = ("Well", "Project", "Type", "Status", "Reports", "Latest report", "Depth (m)", "Days since",
                "Survey MD / TVD (m)", "Survey", "Attention")
KPI_ORDER = ("wells_total", "wells_active", "wells_planning", "wells_completed", "reports_total",
             "reports_window", "latest_report", "npt_window", "npt_share", "wells_need_review", "imports_window")

STYLE = """
QFrame#kpiCard { background: #ffffff; border: 1px solid #d0d5dd; border-radius: 6px; }
QLabel#kpiTitle { color: #475467; font-size: 11px; }
QLabel#kpiValue { font-size: 20px; font-weight: 600; }
QLabel#dashState { color: #475467; }
QLabel#emptyTitle { font-size: 16px; font-weight: 600; color: #344054; }
QGroupBox { font-weight: 600; }
"""


def format_kpi_value(kpi) -> str:
    """Display text of a KPI; None is always "No data", never 0."""
    if kpi.value is None:
        return "No data"
    if isinstance(kpi.value, date):
        return kpi.value.isoformat()
    if isinstance(kpi.value, float):
        text = f"{kpi.value:,.1f}"
    else:
        text = f"{kpi.value:,}"
    return f"{text} {kpi.unit}".strip()


class KpiCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self.title = QLabel("—")
        self.title.setObjectName("kpiTitle")
        self.value = QLabel("…")
        self.value.setObjectName("kpiValue")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        self.kpi = None

    def set_kpi(self, kpi):
        self.kpi = kpi
        self.title.setText(kpi.label)
        self.value.setText(format_kpi_value(kpi))
        self.value.setStyleSheet(f"color: {STATE_COLORS[kpi.state]};")
        self.setToolTip(kpi.definition)


class HomeTab(DrillTabBase):
    """Operations dashboard."""

    navigate_requested = Signal(dict)

    def __init__(self, db_manager, parent=None):
        super().__init__("HomeTab", db_manager, parent)
        self.db = db_manager
        self.db_manager = db_manager
        self.parent_window = parent           # MainWindow (backup service, autosave, tabs)
        self.parent_tab_widget = None
        self.status_manager.register_widget("HomeTab", self)
        self.snapshot = None
        self.last_update: Optional[datetime] = None
        self.backup_info = None
        self._worker = None
        self._refresh_pending = False
        self.load_count = 0
        self.init_ui()
        # First load on the next event-loop turn, once the main window is built.
        QTimer.singleShot(0, self.load_data)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.load_data)
        self.refresh_timer.start(300_000)     # every 5 minutes

    # ------------------------------------------------------------------ UI
    def init_ui(self):
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Operations Dashboard")
        title.setFont(QFont("Arial", 17, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        self.state_label = QLabel("Loading…")
        self.state_label.setObjectName("dashState")
        header.addWidget(self.state_label)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load_data)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(8)
        self.kpi_cards = {}
        for index, key in enumerate(KPI_ORDER):
            card = KpiCard()
            self.kpi_cards[key] = card
            self.kpi_grid.addWidget(card, index // 6, index % 6)
        layout.addLayout(self.kpi_grid)

        self.empty_panel = QFrame()
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_title = QLabel("No wells yet")
        empty_title.setObjectName("emptyTitle")
        empty_text = QLabel("Create a well, or import a daily drilling report, to populate the dashboard.")
        empty_buttons = QHBoxLayout()
        for text, slot in (("New well", self.open_new_well_tab), ("Import DDR", self.import_ddr)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            empty_buttons.addWidget(button)
        empty_buttons.addStretch()
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_text)
        empty_layout.addLayout(empty_buttons)
        self.empty_panel.setVisible(False)
        layout.addWidget(self.empty_panel)

        self.content = QSplitter(Qt.Horizontal)
        wells_box = QGroupBox("Wells")
        wells_layout = QVBoxLayout(wells_box)
        self.wells_table = QTableWidget(0, len(WELL_COLUMNS))
        self.wells_table.setHorizontalHeaderLabels(WELL_COLUMNS)
        self.wells_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.wells_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.wells_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.wells_table.verticalHeader().setVisible(False)
        self.wells_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.wells_table.horizontalHeader().setStretchLastSection(True)
        # Snapshot order (needs-attention first) until the user sorts by a column.
        self.wells_table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.wells_table.cellDoubleClicked.connect(lambda row, _column: self.open_selected_well())
        wells_layout.addWidget(self.wells_table)
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
        wells_layout.addLayout(actions)
        self.wells_table.itemSelectionChanged.connect(self._update_well_actions)
        self.content.addWidget(wells_box)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        attention_box = QGroupBox("Needs attention")
        attention_layout = QVBoxLayout(attention_box)
        self.attention_list = QListWidget()
        self.attention_list.setWordWrap(True)
        self.attention_list.itemDoubleClicked.connect(self._attention_activated)
        attention_layout.addWidget(self.attention_list)
        side_layout.addWidget(attention_box, 3)
        recent_box = QGroupBox("Recent daily reports")
        recent_layout = QVBoxLayout(recent_box)
        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels(("Date", "Well", "#", "Depth (m)", "Status"))
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.cellDoubleClicked.connect(self._recent_activated)
        recent_layout.addWidget(self.recent_table)
        side_layout.addWidget(recent_box, 2)
        system_box = QGroupBox("System")
        system_layout = QGridLayout(system_box)
        self.system_labels = {}
        for row, key in enumerate(("Database", "Last verified backup", "Autosave")):
            system_layout.addWidget(QLabel(key + ":"), row, 0)
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            system_layout.addWidget(value, row, 1)
            self.system_labels[key] = value
        side_layout.addWidget(system_box)
        self.content.addWidget(side)
        self.content.setStretchFactor(0, 3)
        self.content.setStretchFactor(1, 2)
        layout.addWidget(self.content, 1)

        quick = QHBoxLayout()
        for text, slot in (("New daily report", self.new_report), ("Import DDR", self.import_ddr),
                           ("New well", self.open_new_well_tab), ("Export Center", self.export_data),
                           ("Analysis", self.open_analysis_tab)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            quick.addWidget(button)
        quick.addStretch()
        layout.addLayout(quick)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # -------------------------------------------------------------- loading
    def _snapshot_job(self):
        backup_service = getattr(self.parent_window, "backup_service", None)
        today = date.today()

        def job(db):
            from core.operations_dashboard import build_snapshot
            snapshot = build_snapshot(db, today=today)
            backup = None
            if backup_service is not None:
                try:
                    found = backup_service.list_backups(deep=False)
                    backup = ("found", found[0][1].get("created_utc")) if found else ("none", None)
                except OSError as exc:
                    backup = ("unavailable", type(exc).__name__)
            return snapshot, backup
        return job

    def load_data(self):
        """Reload the dashboard; queued if a load is already running."""
        if self.db is None:
            return
        if self._worker is not None:
            self._refresh_pending = True
            return
        self.state_label.setText("Loading…")
        self.refresh_btn.setEnabled(False)
        job = self._snapshot_job()
        from core.export_jobs import has_isolated_reader
        if has_isolated_reader(self.db):
            from core.async_workers import ReadOnlyQueryWorker
            worker = ReadOnlyQueryWorker(self.db, job, self)
            worker.completed.connect(self._on_loaded)
            worker.failed.connect(self._on_failed)
            worker.finished.connect(self._on_worker_finished)
            self._worker = worker
            worker.start()
            return
        try:
            result = job(self.db)
        except Exception as exc:
            logger.warning("Dashboard load failed: %s", type(exc).__name__)
            self._on_failed(type(exc).__name__)
        else:
            self._on_loaded(result)
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
        """Block until a running load finishes (tests and shutdown)."""
        worker = self._worker
        if worker is None:
            return True
        finished = worker.wait(timeout_ms)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        return finished

    def _on_failed(self, error_type: str):
        stale = f" — showing data from {self.last_update:%H:%M:%S}" if self.last_update else ""
        self.state_label.setText(f"Load failed ({error_type}){stale}")
        self.state_label.setStyleSheet(f"color: {SEVERITY_COLORS['error']};")

    def _on_loaded(self, result):
        snapshot, backup = result
        self.snapshot, self.backup_info = snapshot, backup
        self.last_update = datetime.now()
        self.load_count += 1
        self.state_label.setStyleSheet("")
        self.state_label.setText(f"Updated {self.last_update:%H:%M:%S} · data as of {snapshot.today.isoformat()}")
        for key, card in self.kpi_cards.items():
            card.set_kpi(snapshot.kpis[key])
        self.empty_panel.setVisible(snapshot.empty)
        self.content.setVisible(not snapshot.empty)
        self._fill_wells(snapshot)
        self._fill_attention(snapshot)
        self._fill_recent(snapshot)
        self._fill_system(backup)

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

    def _fill_wells(self, snapshot):
        table = self.wells_table
        table.setSortingEnabled(False)
        table.setRowCount(len(snapshot.wells))
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
                self._item(well.project),
                self._item(well.well_type or "—"),
                self._item(well.status),
                self._item(str(well.report_count), True),
                self._item(latest),
                self._item(depth, True, color=SEVERITY_COLORS["warning"] if depth == "not reported" else None),
                self._item("—" if well.days_since_report is None else str(well.days_since_report), True),
                self._item(survey, True),
                self._item(SURVEY_LABELS.get(well.survey_status, well.survey_status),
                           color=SEVERITY_COLORS["warning"] if well.survey_status == "REVIEW_REQUIRED" else None),
                self._item(attention, color=SEVERITY_COLORS.get(worst) if worst else "#1e7b34"),
            )
            for column, item in enumerate(values):
                table.setItem(row, column, item)
        table.setSortingEnabled(True)
        self._update_well_actions()

    def _fill_attention(self, snapshot):
        self.attention_list.clear()
        if not snapshot.attention:
            item = QListWidgetItem("Nothing needs attention.")
            item.setForeground(QColor("#1e7b34"))
            self.attention_list.addItem(item)
            return
        for flag in snapshot.attention:
            item = QListWidgetItem(f"{flag.severity.upper()} · {flag.well_name}: {flag.message}")
            item.setForeground(QColor(SEVERITY_COLORS[flag.severity]))
            item.setData(Qt.UserRole, flag)
            item.setToolTip("Double-click to open")
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
        if row < 0 or self.snapshot is None:
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
        if well:
            self._navigate({"type": "well_tab", "well_id": well.well_id, "tab_title": "Trajectory",
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
        else:
            self._navigate({"type": "well", "id": flag.well_id})

    def _recent_activated(self, row, _column):
        item = self.recent_table.item(row, 0)
        report = item.data(Qt.UserRole) if item else None
        if report:
            self._navigate({"type": "daily_report", "id": report["report_id"], "report_id": report["report_id"],
                            "section_id": report["section_id"], "well_id": report["well_id"]})

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
