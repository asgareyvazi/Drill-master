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
* M52: a "Compare / clearance" tab (``tabs.trajectory_compare_panel``) compares
  the well with a plan file or an offset well - screening only, labelled so.

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
        from tabs.trajectory_layers_panel import TrajectoryLayersPanel
        # M132. The unit getter is the combo's bound method, never a lambda over ``self``: a closure would tie the
        # viewer and the panel into a reference cycle (M50: a disposed 3D view must leave no cyclic Qt garbage).
        self.layers_panel = TrajectoryLayersPanel(self.db_manager, unit_getter=self.unit_combo.currentData)
        self.view3d.add_layer_controls(self.layers_panel)
        self.layers_panel.working_selected.connect(self._render_working_3d)
        self.layers_panel.layers_ready.connect(self._render_layers_3d)
        from core.selection_manager import SelectionManager
        SelectionManager().wellbore_changed.connect(self._sync_layers)
        SelectionManager().selection_cleared.connect(self._sync_layers)
        from tabs.trajectory_compare_panel import TrajectoryComparePanel
        self.compare_panel = TrajectoryComparePanel(self.db_manager)     # M52 screening comparison
        self.view_tabs.addTab(self.compare_panel, "Compare / clearance")
        from tabs.well_plan_designer_panel import WellPlanDesignerPanel
        self.plan_designer = WellPlanDesignerPanel(handover=True, db_manager=self.db_manager)  # M55/M62 planning aid
        self.plan_designer.plan_ready.connect(self.use_designed_plan)
        self.view_tabs.addTab(self.plan_designer, "Plan designer")
        from tabs.survey_revision_panel import SurveyRevisionPanel
        self.survey_revisions = SurveyRevisionPanel(self.db_manager)      # M72 immutable survey revisions
        self.survey_revisions.revision_saved.connect(lambda _id: self.plan_designer.refresh_tie_ins())
        self.view_tabs.addTab(self.survey_revisions, "Survey revisions")
        from tabs.trajectory_saved_views_panel import TrajectorySavedViewsPanel
        self.saved_views = TrajectorySavedViewsPanel(self.db_manager)    # M178 named, revisioned saved views
        self.saved_views.view_opened.connect(self.show_saved_view)
        self.survey_revisions.revision_saved.connect(self.saved_views.refresh)
        self.view_tabs.addTab(self.saved_views, "Saved views")
        self.saved_view = None          # the saved view currently drawn instead of the live data (M178)
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
        well_changed = well_id != self.well_id
        self.well_id, self.report_id = well_id, report_id
        designer = getattr(self, "plan_designer", None)
        if designer is not None:
            designer.set_well(well_id)
        revisions = getattr(self, "survey_revisions", None)
        if revisions is not None:
            revisions.set_well(well_id)
        saved = getattr(self, "saved_views", None)
        if saved is not None and well_changed:
            saved.set_well(well_id)
        if well_changed:
            self.compare_panel.set_well(well_id)
        self.reload()
        if well_changed:
            self._sync_layers()

    def _sync_layers(self, *_args):
        """M132: the layer records follow the well and the explicitly selected wellbore (M124 identity)."""
        from core.selection_manager import SelectionManager

        wellbore = SelectionManager().wellbore_for(self.well_id) if self.well_id else None
        if (self.well_id, wellbore) != (self.layers_panel.well_id, self.layers_panel.wellbore_id):
            self.layers_panel.set_scope(self.well_id, wellbore)

    def _render_working_3d(self):
        t = self.trajectory
        if t is None:
            self.view3d.clear("Select a well to view its trajectory.")
            return
        self.view3d.render(scene_from_trajectory(t, self.unit), equal_scale=self.aspect_check.isChecked())

    def _render_layers_3d(self, layer_set):
        self.view3d.render_layers(layer_set, equal_scale=self.aspect_check.isChecked())

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return self.layers_panel.shutdown(timeout_ms)

    def select_well(self, well_id: Optional[int]):
        self.set_context(well_id, self.report_id)

    def _vs_mode_changed(self):
        self.vs_spin.setEnabled(self.vs_mode_combo.currentData() == "user")
        self.reload()

    @property
    def unit(self) -> str:
        return self.unit_combo.currentData()

    def view_settings(self) -> dict:
        """M178: the viewer settings a saved view records (``core.trajectory_views.DEFAULT_SETTINGS`` keys)."""
        user = self.vs_mode_combo.currentData() == "user"
        return {"scope": self.scope_combo.currentData(), "unit": self.unit_combo.currentData(),
                "vs_mode": self.vs_mode_combo.currentData(), "vs_azimuth": self.vs_spin.value() if user else None,
                "show_stations": self.points_check.isChecked(), "equal_scale": self.aspect_check.isChecked()}

    def _push_saved_view_context(self) -> None:
        saved = getattr(self, "saved_views", None)
        if saved is None:
            return
        from core.selection_manager import SelectionManager

        wellbore = SelectionManager().wellbore_for(self.well_id, self.db_manager) if self.well_id else None
        saved.set_viewer_context(well_id=self.well_id, report_id=self.report_id, wellbore_id=wellbore,
                                 settings=self.view_settings())

    def _apply_settings(self, settings: dict) -> None:
        widgets = (self.scope_combo, self.unit_combo, self.vs_mode_combo, self.vs_spin, self.points_check,
                   self.aspect_check)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            for combo, key in ((self.scope_combo, "scope"), (self.unit_combo, "unit"),
                               (self.vs_mode_combo, "vs_mode")):
                index = combo.findData(settings.get(key))
                if index >= 0:
                    combo.setCurrentIndex(index)
            user = settings.get("vs_mode") == "user"
            self.vs_spin.setEnabled(user)
            if user and settings.get("vs_azimuth") is not None:
                self.vs_spin.setValue(float(settings["vs_azimuth"]))
            self.points_check.setChecked(bool(settings.get("show_stations", True)))
            self.aspect_check.setChecked(bool(settings.get("equal_scale", True)))
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def show_saved_view(self, revision_id: int) -> bool:
        """M178: draw the stored snapshot of a saved view (never recomputed); the banner states the drift of the
        current data against it. "Reload" returns to the live data."""
        from core import trajectory_views as tv
        from core.well_trajectory import ComposedStation, TrajectoryIssue, WellTrajectory

        record = tv.get_view(self.db_manager, revision_id) if self.db_manager is not None else None
        if record is None or record["integrity"] != "VERIFIED" or record["well_id"] != self.well_id:
            why = ("it belongs to another well" if record is not None and record["well_id"] != self.well_id
                   else f"its snapshot is {record['integrity']}" if record is not None else "it does not exist")
            self._set_banner(ERROR, f"The saved view is not shown: {why}.")
            return False
        state = tv.drift(self.db_manager, record)
        summary = record["trajectory"]
        stations = [ComposedStation(md=s["md"], inc=s["inc"], azi=s["azi"], tvd=s["tvd"], north=s["north"],
                                    east=s["east"], vs=s["vs"], hd=s["hd"], dls=s["dls"],
                                    report_ids=tuple(s.get("report_ids") or ())) for s in record["stations"]]
        issues = [TrajectoryIssue(i["code"], i["severity"], i["message"], i.get("md"))
                  for i in summary.get("issues", [])]
        self.trajectory = WellTrajectory(
            status=summary.get("status", READY), stations=stations, issues=issues,
            vs_azimuth=summary.get("vs_azimuth"), vs_azimuth_source=summary.get("vs_azimuth_source", "none"),
            closure_distance=summary.get("closure_distance"), closure_azimuth=summary.get("closure_azimuth"),
            input_rows=summary.get("input_rows", 0), excluded_rows=summary.get("excluded_rows", 0))
        self.stations = list(stations)
        self.selected_index = None
        self._apply_settings(record["settings"])
        self.saved_view = (record, state)
        self.render()
        return True

    def reload(self):
        """Read the stations and recompose the trajectory."""
        self.saved_view = None
        self.selected_index = None
        self._push_saved_view_context()
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
            self._report_working()
            return
        vs_azimuth = self.vs_spin.value() if self.vs_mode_combo.currentData() == "user" else None
        try:
            rows = self.db_manager.load_survey_points(well_id=self.well_id, report_id=scope_report)
        except Exception as exc:
            logger.warning("Trajectory viewer could not read surveys: %s", type(exc).__name__)
            self.trajectory, self.stations = None, []
            self._set_banner(ERROR, f"Survey stations could not be read ({type(exc).__name__}).")
            self._clear("Survey stations could not be read; nothing is drawn.")
            self._report_working(readable=False)
            return
        self.trajectory = compose_well_trajectory(rows, vs_azimuth=vs_azimuth)
        self.stations = list(self.trajectory.stations)
        self._report_working()
        self.render()

    def _report_working(self, readable: bool = True) -> None:
        """M138: tell the 3D layer panel what the working survey really holds (its row never claims DRAWN for
        a scope without stations)."""
        panel = getattr(self, "layers_panel", None)
        if panel is not None:
            t = self.trajectory
            panel.set_working_state(len(self.stations) if readable else None, bool(t is not None and t.drawable))

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
        prefix = ""
        if self.saved_view is not None:
            record, state = self.saved_view
            prefix = (f"SAVED VIEW '{record['name']}' revision {record['revision']} ({record['status']}) — stored "
                      f"snapshot; current data: {state.state}. {state.reason} ")
        self._set_banner(t.status, prefix + reasons.get(t.status, "") + (" " if t.status in reasons else "")
                         + self.summary_text())
        self._push_saved_view_context()
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
        # The 3D view draws only a drawable trajectory; otherwise it states why. M132: with a revision base the
        # layers are rebuilt instead (units / scale may have changed).
        from tabs.trajectory_layers_panel import WORKING
        if self.layers_panel.choices()["base"] == WORKING:
            self.view3d.render(scene_from_trajectory(t, self.unit), equal_scale=self.aspect_check.isChecked())
        else:
            self.layers_panel.refresh()
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

    def use_designed_plan(self, rows, source) -> bool:
        """Hand a designed plan to the plan-vs-actual comparison and show it."""
        accepted = self.compare_panel.set_plan_rows(rows, source,
                                                    targets=getattr(self.plan_designer, "handover_targets", None),
                                                    reference=getattr(self.plan_designer, "handover_reference", None))
        if accepted:
            self.view_tabs.setCurrentWidget(self.compare_panel)
        return accepted

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
