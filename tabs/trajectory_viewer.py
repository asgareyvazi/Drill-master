"""Interactive whole-well trajectory viewer (M44).

Plan view (East/North) and vertical section (VS/TVD) of the trajectory that
``core.well_trajectory`` recomposes from the stored MD/Inc/Azi stations of
every report of the selected well (or of one report).  The viewer adds no
engineering calculation; it only presents ``WellTrajectory`` results.

* Nothing is drawn unless the result is drawable (>= 2 computed stations);
  otherwise the banner states why.
* Excluded stations (missing angles, conflicting repeated readings) are
  listed with their MD; they are never drawn.
* Units: stored metres / deg/30 m; feet and deg/100 ft are display
  conversions only.
* The VS azimuth is the closure azimuth of the last station unless the user
  enters one; the banner always states which.
* M45: a "3D view" tab shows the same composed stations in 3D
  (``core.trajectory_3d``; East/North/TVD-down, same units, equal scale by
  default).  Picking a station there selects the same station everywhere.

Survey reads for one well are small (one indexed query), so loading runs on
the UI thread.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from core.trajectory_3d import scene_from_trajectory
from core.well_trajectory import (
    ERROR, INSUFFICIENT_DATA, NO_DATA, READY, REVIEW_REQUIRED, compose_well_trajectory, dls_for_display,
    to_display_units,
)

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover  # silent-ok: pyqtgraph is required; without it the viewer shows a 'charts unavailable' message
    pg = None
    PYQTGRAPH_AVAILABLE = False

STATUS_STYLE = {
    READY: ("#e8f6ec", "#1e7b34", "Ready"),
    REVIEW_REQUIRED: ("#fff4e0", "#9a5b00", "Review required"),
    INSUFFICIENT_DATA: ("#eef0f2", "#4a5560", "Insufficient data"),
    NO_DATA: ("#eef0f2", "#4a5560", "No survey data"),
    ERROR: ("#fdecea", "#a61b1b", "Error"),
}
SEVERITY_COLOR = {"error": "#a61b1b", "warning": "#9a5b00", "info": "#4a5560"}
TABLE_COLUMNS = ("MD", "Inc (°)", "Azi (°)", "TVD", "North", "East", "VS", "DLS", "Reports")


class TrajectoryViewerTab(QWidget):
    """Whole-well plan and vertical-section views with station inspection."""

    station_selected = Signal(int)

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.well_id: Optional[int] = None
        self.report_id: Optional[int] = None
        self.trajectory = None
        self.stations: list = []
        self.selected_index: Optional[int] = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Whole well (all reports)", "well")
        self.scope_combo.addItem("Selected report only", "report")
        self.unit_combo = QComboBox()
        self.unit_combo.addItem("Metres (m, °/30 m)", "m")
        self.unit_combo.addItem("Feet (ft, °/100 ft)", "ft")
        self.vs_mode_combo = QComboBox()
        self.vs_mode_combo.addItem("Closure azimuth", "closure")
        self.vs_mode_combo.addItem("Custom azimuth", "user")
        self.vs_spin = QDoubleSpinBox()
        self.vs_spin.setRange(0.0, 359.99)
        self.vs_spin.setDecimals(2)
        self.vs_spin.setSuffix(" °")
        self.vs_spin.setEnabled(False)
        self.points_check = QCheckBox("Show stations")
        self.points_check.setChecked(True)
        self.aspect_check = QCheckBox("Equal axis scale")
        self.aspect_check.setChecked(True)
        self.refresh_button = QPushButton("Reload")
        for label, widget in (("Scope:", self.scope_combo), ("Units:", self.unit_combo),
                              ("VS azimuth:", self.vs_mode_combo)):
            controls.addWidget(QLabel(label))
            controls.addWidget(widget)
        controls.addWidget(self.vs_spin)
        controls.addWidget(self.points_check)
        controls.addWidget(self.aspect_check)
        controls.addStretch()
        controls.addWidget(self.refresh_button)
        layout.addLayout(controls)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.banner)

        splitter = QSplitter(Qt.Horizontal)
        self.view_tabs = QTabWidget()
        if PYQTGRAPH_AVAILABLE:
            self.plan_plot = self._make_plot("Plan view (true north up)")
            self.section_plot = self._make_plot("Vertical section")
            self.section_plot.invertY(True)
            self.view_tabs.addTab(self.plan_plot, "Plan view")
            self.view_tabs.addTab(self.section_plot, "Vertical section")
        else:
            self.plan_plot = self.section_plot = None
            self.view_tabs.addTab(QLabel("Plots need pyqtgraph (a core requirement)."), "Plots")
        from tabs.trajectory_3d_view import Trajectory3DView
        self.view3d = Trajectory3DView()
        self.view_tabs.addTab(self.view3d, "3D view")
        self.view3d.station_picked.connect(self.select_station)
        splitter.addWidget(self.view_tabs)

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        info_box = QGroupBox("Selected station")
        form = QFormLayout(info_box)
        self.info_labels = {}
        for key in ("MD", "Inclination", "Azimuth", "TVD", "North / East", "Vertical section", "DLS", "Source"):
            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(key + ":", value)
            self.info_labels[key] = value
        side_layout.addWidget(info_box)
        issues_box = QGroupBox("Data checks")
        issues_layout = QVBoxLayout(issues_box)
        self.issue_list = QListWidget()
        self.issue_list.setMaximumHeight(150)
        self.issue_list.setWordWrap(True)
        issues_layout.addWidget(self.issue_list)
        side_layout.addWidget(issues_box)
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        side_layout.addWidget(self.table, 1)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.scope_combo.currentIndexChanged.connect(self.reload)
        self.unit_combo.currentIndexChanged.connect(self.render)
        self.vs_mode_combo.currentIndexChanged.connect(self._vs_mode_changed)
        self.vs_spin.editingFinished.connect(self.reload)
        self.points_check.toggled.connect(self.render)
        self.aspect_check.toggled.connect(self.render)
        self.refresh_button.clicked.connect(self.reload)
        self.table.itemSelectionChanged.connect(self._table_selection_changed)
        self._set_banner(NO_DATA, "Select a well to view its trajectory.")

    def _make_plot(self, title):
        widget = pg.PlotWidget(background="w")
        widget.setTitle(title, color="#2c3e50")
        widget.showGrid(x=True, y=True, alpha=0.25)
        plot = widget.getPlotItem()
        for name in ("left", "bottom"):
            axis = plot.getAxis(name)
            axis.setPen(pg.mkPen("#4a5560"))
            axis.setTextPen(pg.mkPen("#2c3e50"))
        return widget

    # ------------------------------------------------------------- context
    def set_context(self, well_id: Optional[int], report_id: Optional[int] = None):
        self.well_id, self.report_id = well_id, report_id
        self.reload()

    def select_well(self, well_id: Optional[int]):
        self.set_context(well_id, self.report_id)

    def _vs_mode_changed(self):
        self.vs_spin.setEnabled(self.vs_mode_combo.currentData() == "user")
        self.reload()

    @property
    def unit(self) -> str:
        return self.unit_combo.currentData()

    def reload(self):
        """Read the stations and recompose the trajectory."""
        self.selected_index = None
        if not self.well_id or self.db_manager is None:
            self.trajectory, self.stations = None, []
            self._set_banner(NO_DATA, "Select a well to view its trajectory.")
            self._clear()
            return
        scope_report = self.report_id if self.scope_combo.currentData() == "report" else None
        if self.scope_combo.currentData() == "report" and not self.report_id:
            self.trajectory, self.stations = None, []
            self._set_banner(NO_DATA, "Select a daily report to use the report scope.")
            self._clear("Select a daily report to use the report scope.")
            return
        vs_azimuth = self.vs_spin.value() if self.vs_mode_combo.currentData() == "user" else None
        try:
            rows = self.db_manager.load_survey_points(well_id=self.well_id, report_id=scope_report)
        except Exception as exc:
            logger.warning("Trajectory viewer could not read surveys: %s", type(exc).__name__)
            self.trajectory, self.stations = None, []
            self._set_banner(ERROR, f"Survey stations could not be read ({type(exc).__name__}).")
            self._clear("Survey stations could not be read; nothing is drawn.")
            return
        self.trajectory = compose_well_trajectory(rows, vs_azimuth=vs_azimuth)
        self.stations = list(self.trajectory.stations)
        self.render()

    # -------------------------------------------------------------- render
    def _set_banner(self, status, text):
        background, foreground, title = STATUS_STYLE[status]
        self.banner.setText(f"<b>{title}</b> — {text}")
        self.banner.setStyleSheet(
            f"QLabel {{ background: {background}; color: {foreground}; border: 1px solid {foreground};"
            " border-radius: 4px; padding: 6px 10px; }")
        self.banner.setProperty("status", status)

    def _clear(self, message: str = ""):
        for plot in (self.plan_plot, self.section_plot):
            if plot is not None:
                plot.clear()
        self.view3d.clear(message or "Select a well to view its trajectory.")
        self.table.setRowCount(0)
        self.issue_list.clear()
        for label in self.info_labels.values():
            label.setText("—")

    def _length(self, value):
        converted = to_display_units(value, self.unit)
        return "—" if converted is None else f"{converted:,.2f} {self.unit}"

    def summary_text(self) -> str:
        t = self.trajectory
        if t is None:
            return ""
        parts = [f"{len(t.stations)} station(s) from {t.input_rows} stored row(s)"]
        if t.excluded_rows:
            parts.append(f"{t.excluded_rows} excluded")
        if t.vs_azimuth is not None:
            source = {"closure": "closure", "user": "custom", "default_north": "north, closure undefined"}
            parts.append(f"VS azimuth {t.vs_azimuth:.2f}° ({source.get(t.vs_azimuth_source, t.vs_azimuth_source)})")
        if t.closure_distance is not None:
            closure = self._length(t.closure_distance)
            if t.closure_azimuth is not None:
                closure += f" @ {t.closure_azimuth:.2f}°"
            parts.append(f"closure {closure}")
        return " · ".join(parts)

    def render(self):
        self._clear()
        t = self.trajectory
        if t is None:
            return
        reasons = {
            NO_DATA: "No survey stations are stored for this scope.",
            INSUFFICIENT_DATA: "At least two valid stations are needed to draw a path.",
            ERROR: "The trajectory could not be computed.",
        }
        self._set_banner(t.status, reasons.get(t.status, "") + (" " if t.status in reasons else "")
                         + self.summary_text())
        for issue in t.issues:
            where = f"MD {self._length(issue.md)}: " if issue.md is not None else ""
            item = QListWidgetItem(f"[{issue.severity}] {where}{issue.message}")
            item.setForeground(QColor(SEVERITY_COLOR[issue.severity]))
            item.setToolTip(item.text())
            item.setData(Qt.UserRole, issue.code)
            self.issue_list.addItem(item)
        self._fill_table()
        if t.drawable and self.plan_plot is not None:
            self._draw(t)
        # The 3D view draws only a drawable trajectory; otherwise it states why.
        self.view3d.render(scene_from_trajectory(t, self.unit), equal_scale=self.aspect_check.isChecked())
        if self.selected_index is not None:       # keep the selection across unit/option changes
            self.select_station(self.selected_index)

    def _draw(self, t):
        """Plot the computed path; only called for a drawable trajectory."""
        unit = self.unit
        east = [to_display_units(s.east, unit) for s in self.stations]
        north = [to_display_units(s.north, unit) for s in self.stations]
        vs = [to_display_units(s.vs, unit) for s in self.stations]
        tvd = [to_display_units(s.tvd, unit) for s in self.stations]
        symbol = "o" if self.points_check.isChecked() else None
        pen = pg.mkPen("#1f6fb2", width=2)
        brush = pg.mkBrush("#1f6fb2")
        self.plan_plot.setLabel("bottom", f"East ({unit})")
        self.plan_plot.setLabel("left", f"North ({unit})")
        self.section_plot.setLabel("bottom", f"Vertical section ({unit}) @ {t.vs_azimuth:.2f}°")
        self.section_plot.setLabel("left", f"TVD ({unit})")
        self.plan_plot.plot(east, north, pen=pen, symbol=symbol, symbolSize=6, symbolBrush=brush)
        self.section_plot.plot(vs, tvd, pen=pen, symbol=symbol, symbolSize=6, symbolBrush=brush)
        # Section plane direction through the tie-on point.
        import math
        reach = max(max(abs(v) for v in east + north), 1.0)
        rad = math.radians(t.vs_azimuth)
        self.plan_plot.plot([0, reach * math.sin(rad)], [0, reach * math.cos(rad)],
                            pen=pg.mkPen("#7f8c8d", width=1, style=Qt.DashLine))
        for plot, xs, ys in ((self.plan_plot, east, north), (self.section_plot, vs, tvd)):
            scatter = pg.ScatterPlotItem(xs, ys, size=12, pen=None, brush=pg.mkBrush(0, 0, 0, 0),
                                         data=list(range(len(xs))))
            scatter.sigClicked.connect(self._scatter_clicked)
            plot.addItem(scatter)
            plot.addItem(pg.ScatterPlotItem([xs[0]], [ys[0]], symbol="s", size=10,
                                            brush=pg.mkBrush("#27ae60"), pen=pg.mkPen("#1e7b34")))
            plot.addItem(pg.ScatterPlotItem([xs[-1]], [ys[-1]], symbol="t", size=12,
                                            brush=pg.mkBrush("#c0392b"), pen=pg.mkPen("#8e2a20")))
        # Equal scales by default: an auto-scaled section turns 0.4 m of VS
        # over 100 m of TVD into an apparent 45 deg slant.
        self.plan_plot.setAspectLocked(self.aspect_check.isChecked())
        self.section_plot.setAspectLocked(self.aspect_check.isChecked())
        self.plan_plot.autoRange()
        self.section_plot.autoRange()

    def _fill_table(self):
        unit = self.unit
        dls_unit = "deg/30m" if unit == "m" else "deg/100ft"
        headers = list(TABLE_COLUMNS)
        for index, name in ((0, "MD"), (3, "TVD"), (4, "North"), (5, "East"), (6, "VS")):
            headers[index] = f"{name} ({unit})"
        headers[7] = "DLS (°/30 m)" if unit == "m" else "DLS (°/100 ft)"
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.stations))
        for row, s in enumerate(self.stations):
            values = (to_display_units(s.md, unit), s.inc, s.azi, to_display_units(s.tvd, unit),
                      to_display_units(s.north, unit), to_display_units(s.east, unit),
                      to_display_units(s.vs, unit), dls_for_display(s.dls, dls_unit))
            for column, value in enumerate(values):
                item = QTableWidgetItem(f"{value:,.2f}")
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setData(Qt.UserRole, row)
                self.table.setItem(row, column, item)
            self.table.setItem(row, 8, QTableWidgetItem(", ".join(str(r) for r in s.report_ids) or "—"))

    # ----------------------------------------------------------- selection
    def _scatter_clicked(self, _item, points, *_args):
        if points:
            self.select_station(int(points[0].data()))

    def _table_selection_changed(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) == 1:
            row = rows.pop()
            if row != self.selected_index:
                self.select_station(row)

    def select_station(self, index: int):
        if not 0 <= index < len(self.stations):
            return
        self.selected_index = index
        s = self.stations[index]
        unit = self.unit
        dls_unit = "deg/30m" if unit == "m" else "deg/100ft"
        dls_label = "°/30 m" if unit == "m" else "°/100 ft"
        self.info_labels["MD"].setText(self._length(s.md))
        self.info_labels["Inclination"].setText(f"{s.inc:.2f}°")
        self.info_labels["Azimuth"].setText(f"{s.azi:.2f}°")
        self.info_labels["TVD"].setText(self._length(s.tvd))
        self.info_labels["North / East"].setText(f"{self._length(s.north)} / {self._length(s.east)}")
        self.info_labels["Vertical section"].setText(self._length(s.vs))
        self.info_labels["DLS"].setText(f"{dls_for_display(s.dls, dls_unit):.2f} {dls_label}")
        self.info_labels["Source"].setText(
            "report id(s) " + ", ".join(str(r) for r in s.report_ids) if s.report_ids else "—")
        self.table.blockSignals(True)
        self.table.selectRow(index)
        self.table.blockSignals(False)
        self._highlight(index)
        self.station_selected.emit(index)

    def _highlight(self, index):
        if self.trajectory is not None and self.trajectory.drawable:
            self.view3d.highlight(index)
        if self.plan_plot is None or not self.trajectory or not self.trajectory.drawable:
            return
        s = self.stations[index]
        unit = self.unit
        for plot, x, y in ((self.plan_plot, s.east, s.north), (self.section_plot, s.vs, s.tvd)):
            for item in list(plot.listDataItems()) + list(plot.items()):
                if getattr(item, "_m44_highlight", False):
                    plot.removeItem(item)
            marker = pg.ScatterPlotItem([to_display_units(x, unit)], [to_display_units(y, unit)], size=16,
                                        symbol="o", pen=pg.mkPen("#e67e22", width=3), brush=pg.mkBrush(0, 0, 0, 0))
            marker._m44_highlight = True
            plot.addItem(marker)
