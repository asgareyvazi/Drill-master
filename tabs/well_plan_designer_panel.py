"""M55: well plan designer panel (inside the trajectory viewer).

The user enters segments (vertical to KOP / hold, build-drop-turn curve, hold to
TVD), a station step, an optional DLS limit, the vertical-section azimuth and
optional targets. ``core.well_plan_designer`` generates the stations and the
canonical minimum-curvature engine positions them. The panel shows stations,
segment summary, DLS warnings and target hits, exports CSV (method and version
in the header) and can hand the plan to the comparison tab — nothing is
persisted silently. Planning aid only; not an approved well plan.
"""

from __future__ import annotations

import csv
import logging
from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from core import directional_plans as dp
from core.well_plan_designer import METHOD, PLAN_VERSION, design_plan

try:
    import pyqtgraph as pg
except ImportError:  # pragma: no cover  # silent-ok: pyqtgraph is a core requirement; plots then show a message
    pg = None

logger = logging.getLogger(__name__)

SEGMENT_TYPES = (("hold", "Vertical / hold (length m)"), ("curve", "Build / drop / turn (inc, azi, DLS)"),
                 ("hold_to_tvd", "Hold to TVD (m)"))
STATION_COLUMNS = ("MD (m)", "Inc (deg)", "Azi (deg)", "TVD (m)", "North (m)", "East (m)", "VS (m)", "DLS (deg/30m)")


PLOTS = (("inc", "Inclination (deg) vs MD"), ("azi", "Azimuth (deg) vs MD"),
         ("dls", "DLS (deg/30 m) vs MD"), ("tvd", "TVD (m) vs MD"))


SOLVE_FIRST, SOLVE_ALL, SOLVE_S = "first", "all", "s_profile"     # M106 solver modes

class WellPlanDesignerPanel(QWidget):
    """Plan designer.  The designed stations are handed over through ``plan_ready``
    (Qt signal: no Python reference back to the receiver, so an embedding viewer is
    freed deterministically - see tests/test_m50_trajectory_3d_disposal.py) and/or a
    standalone ``use_plan`` callable."""

    plan_ready = Signal(list, str)

    def __init__(self, parent=None, use_plan: Optional[Callable[[list, str], None]] = None,
                 handover: bool = False, db_manager=None):
        super().__init__(parent)
        self.use_plan = use_plan
        self.handover = bool(handover)
        self.handover_targets: list = []
        self.handover_reference: dict = {}
        self.result = None
        self.db_manager = db_manager
        self.well_id: Optional[int] = None
        self.current_plan: Optional[dict] = None      # M62: open saved revision (DTO)
        layout = QVBoxLayout(self)

        # M62: saved, versioned plans of the selected well.
        library = QHBoxLayout()
        library.addWidget(QLabel("Saved plans:"))
        self.plan_combo = QComboBox()
        self.plan_combo.setMinimumWidth(260)
        self.plan_combo.currentIndexChanged.connect(self._plan_selection_changed)
        library.addWidget(self.plan_combo, 1)
        self.open_plan_btn = QPushButton("Open")
        self.open_plan_btn.clicked.connect(self._open_clicked)
        self.save_new_btn = QPushButton("Save as new plan…")
        self.save_new_btn.clicked.connect(self._save_new_clicked)
        self.save_rev_btn = QPushButton("Save revision")
        self.save_rev_btn.setToolTip("Store the current inputs as the next revision; earlier revisions are never changed.")
        self.save_rev_btn.clicked.connect(self._save_revision_clicked)
        self.clone_btn = QPushButton("Clone…")
        self.clone_btn.clicked.connect(self._clone_clicked)
        self.archive_btn = QPushButton("Archive")
        self.archive_btn.clicked.connect(self._archive_clicked)
        self.compare_plan_btn = QPushButton("Compare with open")
        self.compare_plan_btn.setToolTip("Compare the selected saved revision with the open one.")
        self.compare_plan_btn.clicked.connect(self._compare_clicked)
        for button in (self.open_plan_btn, self.save_new_btn, self.save_rev_btn, self.clone_btn,
                       self.archive_btn, self.compare_plan_btn):
            library.addWidget(button)
        layout.addLayout(library)
        self.plan_status_label = QLabel("No saved plan open.")
        self.plan_status_label.setWordWrap(True)
        layout.addWidget(self.plan_status_label)

        layout.addWidget(QLabel("Segments (top to bottom). Planning aid — not an approved well plan."))
        self.segment_table = QTableWidget(0, 5)
        self.segment_table.setHorizontalHeaderLabels(["Type", "Length / TVD (m)", "Inc (deg)", "Azi (deg)",
                                                      "DLS (deg/30m)"])
        self.segment_table.horizontalHeader().setStretchLastSection(True)
        self.segment_table.setMaximumHeight(150)
        layout.addWidget(self.segment_table)
        seg_buttons = QHBoxLayout()
        self.add_segment_btn = QPushButton("Add segment")
        self.add_segment_btn.clicked.connect(self._add_segment_clicked)
        self.remove_segment_btn = QPushButton("Remove segment")
        self.remove_segment_btn.clicked.connect(self._remove_segment)
        seg_buttons.addWidget(self.add_segment_btn)
        seg_buttons.addWidget(self.remove_segment_btn)
        seg_buttons.addStretch(1)
        layout.addLayout(seg_buttons)

        form = QFormLayout()
        self.step_spin = self._spin(1, 500, 30, " m")
        self.dls_limit_spin = self._spin(0, 30, 3, " deg/30m")
        self.dls_limit_spin.setSpecialValueText("no limit")
        self.vs_azimuth_spin = self._spin(0, 359.99, 0, " deg")
        form.addRow("Station step", self.step_spin)
        form.addRow("DLS limit", self.dls_limit_spin)
        form.addRow("Vertical-section azimuth", self.vs_azimuth_spin)
        # M72: start from a station of an immutable survey revision.
        self.tie_combo = QComboBox()
        self.tie_combo.addItem("Surface (MD 0, vertical)", None)
        self.tie_combo.setToolTip("A saved survey revision's last station; the plan records the revision and its hash.")
        form.addRow("Tie-in", self.tie_combo)
        # M105: the plan declares its references; a survey tie-in supplies them and may not be contradicted.
        self.plan_azref_combo = QComboBox()
        self.plan_azref_combo.addItem("— not declared —", "")
        for ref in ("true", "grid", "magnetic"):
            self.plan_azref_combo.addItem(ref, ref)
        self.plan_datum_edit = QLineEdit()
        self.plan_datum_edit.setPlaceholderText("depth datum (e.g. RKB); taken from the survey tie-in")
        form.addRow("Plan azimuth reference", self.plan_azref_combo)
        form.addRow("Plan depth datum", self.plan_datum_edit)
        solve_row = QHBoxLayout()
        self.kop_spin = self._spin(0, 10000, 500, " m")
        self.build_spin = self._spin(0.1, 30, 3, " deg/30m")
        self.solve_btn = QPushButton("Solve to first target")
        self.solve_btn.setToolTip("Closed-form build-and-hold through the first target's centre (vertical tie-in only).")
        self.solve_btn.clicked.connect(self.solve_to_target)
        # M106: solver mode; "first" keeps the M86 behaviour unchanged
        self.solver_mode_combo = QComboBox()
        for label, mode in (("Curve-hold to the first target", SOLVE_FIRST),
                            ("Through all targets (multi-segment)", SOLVE_ALL),
                            ("S-profile to the first target", SOLVE_S)):
            self.solver_mode_combo.addItem(label, mode)
        self.solver_mode_combo.currentIndexChanged.connect(lambda _i: self._solver_mode_changed())
        self.drop_spin = self._spin(0.1, 30, 2, " deg/30m")
        self.final_inc_spin = self._spin(0, 89.9, 0, " deg")
        self.final_hold_spin = self._spin(0, 10000, 0, " m")
        self.max_inc_spin = self._spin(1, 180, 90, " deg")
        for label, widget in (("KOP", self.kop_spin), ("Build", self.build_spin)):
            solve_row.addWidget(QLabel(label))
            solve_row.addWidget(widget)
        solve_row.addWidget(self.solve_btn)
        form.addRow("Target solver", solve_row)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.solver_mode_combo)
        for label, widget in (("Max inc", self.max_inc_spin), ("Drop", self.drop_spin),
                              ("Final inc", self.final_inc_spin), ("Final hold", self.final_hold_spin)):
            mode_row.addWidget(QLabel(label))
            mode_row.addWidget(widget)
        form.addRow("Solver mode", mode_row)
        self._solver_mode_changed()
        layout.addLayout(form)

        layout.addWidget(QLabel("Targets (local north/east from wellhead, TVD below rotary table)"))
        self.target_table = QTableWidget(0, 5)
        self.target_table.setHorizontalHeaderLabels(["Name", "North (m)", "East (m)", "TVD (m)", "Radius (m)"])
        self.target_table.horizontalHeader().setStretchLastSection(True)
        self.target_table.setMaximumHeight(100)
        layout.addWidget(self.target_table)
        target_buttons = QHBoxLayout()
        self.add_target_btn = QPushButton("Add target")
        self.add_target_btn.clicked.connect(self._add_target_clicked)
        target_buttons.addWidget(self.add_target_btn)
        target_buttons.addStretch(1)
        self.design_btn = QPushButton("Design plan")
        self.design_btn.clicked.connect(self.design)
        self.export_btn = QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._choose_export)
        self.use_btn = QPushButton("Use as plan for comparison")
        self.use_btn.clicked.connect(self.send_to_compare)
        for button in (self.design_btn, self.export_btn, self.use_btn):
            target_buttons.addWidget(button)
        layout.addLayout(target_buttons)

        self.summary_label = QLabel("Add segments, then Design plan.")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        self.station_table = QTableWidget(0, len(STATION_COLUMNS))
        self.station_table.setHorizontalHeaderLabels(list(STATION_COLUMNS))
        self.station_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.station_table.horizontalHeader().setStretchLastSection(True)
        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.station_table, "Stations")
        self.plot_widgets = {}
        if pg is not None:
            plots = QWidget()
            grid = QGridLayout(plots)
            for index, (key, title) in enumerate(PLOTS):
                widget = pg.PlotWidget(background="w")
                widget.setTitle(title)
                widget.setLabel("bottom", "MD (m)")
                widget.showGrid(x=True, y=True, alpha=0.3)
                grid.addWidget(widget, index // 2, index % 2)
                self.plot_widgets[key] = widget
            self.result_tabs.addTab(plots, "Plots")
        else:
            self.result_tabs.addTab(QLabel("Plots need pyqtgraph (a core requirement)."), "Plots")
        layout.addWidget(self.result_tabs, 1)
        self._set_result_actions(False)
        self._refresh_plan_actions()

    @staticmethod
    def _spin(lo, hi, value, suffix):
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _set_result_actions(self, enabled: bool):
        self.export_btn.setEnabled(enabled)
        self.use_btn.setEnabled(enabled and (self.use_plan is not None or self.handover))

    def add_segment(self, kind="hold", length=None, inc=None, azi=None, dls=None):
        row = self.segment_table.rowCount()
        self.segment_table.insertRow(row)
        combo = QComboBox()
        for key, label in SEGMENT_TYPES:
            combo.addItem(label, key)
        combo.setCurrentIndex(max(0, combo.findData(kind)))
        self.segment_table.setCellWidget(row, 0, combo)
        for col, value in enumerate((length, inc, azi, dls), start=1):
            self.segment_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))

    def _remove_segment(self):
        row = self.segment_table.currentRow()
        if row >= 0:
            self.segment_table.removeRow(row)

    def add_target(self, name="Target", north=None, east=None, tvd=None, radius=None):
        row = self.target_table.rowCount()
        self.target_table.insertRow(row)
        for col, value in enumerate((name, north, east, tvd, radius)):
            self.target_table.setItem(row, col, QTableWidgetItem("" if value is None else str(value)))

    def _cell(self, table, row, col):
        item = table.item(row, col)
        text = item.text().strip() if item else ""
        if not text:
            return None
        return float(text)

    def gather(self):
        """Segments and targets from the tables; raises ValueError naming the bad cell."""
        segments = []
        for row in range(self.segment_table.rowCount()):
            kind = self.segment_table.cellWidget(row, 0).currentData()
            try:
                length, inc, azi, dls = (self._cell(self.segment_table, row, c) for c in range(1, 5))
            except ValueError:
                raise ValueError(f"Segment {row + 1}: values must be numbers") from None
            if kind == "hold":
                if length is None:
                    raise ValueError(f"Segment {row + 1}: enter the hold length")
                segments.append({"type": "hold", "length": length})
            elif kind == "curve":
                if inc is None or dls is None:
                    raise ValueError(f"Segment {row + 1}: enter the target inclination and DLS")
                segment = {"type": "curve", "inc": inc, "dls": dls}
                if azi is not None:
                    segment["azi"] = azi
                segments.append(segment)
            else:
                if length is None:
                    raise ValueError(f"Segment {row + 1}: enter the target TVD in the Length / TVD column")
                segments.append({"type": "hold_to_tvd", "tvd": length})
        targets = []
        for row in range(self.target_table.rowCount()):
            name_item = self.target_table.item(row, 0)
            try:
                north, east, tvd, radius = (self._cell(self.target_table, row, c) for c in range(1, 5))
            except ValueError:
                raise ValueError(f"Target {row + 1}: values must be numbers") from None
            if None in (north, east, tvd):
                raise ValueError(f"Target {row + 1}: north, east and TVD are required")
            targets.append({"name": name_item.text() if name_item else f"Target {row + 1}", "north": north,
                            "east": east, "tvd": tvd, "radius": radius or 0.0})
        return segments, targets

    def design(self):
        self._set_result_actions(False)
        self.station_table.setRowCount(0)
        try:
            segments, targets = self.gather()
        except ValueError as exc:
            self.result = None
            self.summary_label.setText(f"Not designed: {exc}.")
            return None
        limit = self.dls_limit_spin.value() or None
        try:
            tie_in = self.tie_in()
        except Exception as exc:          # a revision that cannot be read is shown, never replaced by the surface
            self.result = None
            self.summary_label.setText(f"Not designed: the survey tie-in could not be read ({exc}).")
            return None
        result = design_plan(segments, step=self.step_spin.value(), dls_limit=limit,
                             vs_azimuth=self.vs_azimuth_spin.value(), targets=targets, tie_in=tie_in)
        self.result = result
        if not result.ok:
            self.summary_label.setText(f"Not designed: {result.error}")
            return result
        for station in result.stations:
            row = self.station_table.rowCount()
            self.station_table.insertRow(row)
            for col, key in enumerate(("md", "inc", "azi", "tvd", "north", "east", "vs", "dls")):
                self.station_table.setItem(row, col, QTableWidgetItem(f"{station[key]:.2f}"))
        last = result.stations[-1]
        lines = [f"{len(result.stations)} stations to MD {last['md']:.1f} m, TVD {last['tvd']:.1f} m. {METHOD}."]
        lines += [f"{s['type']}: MD {s['start_md']:.1f}–{s['end_md']:.1f} m"
                  + (f" at {s['dls']:.2f} deg/30m" if s["dls"] else "") for s in result.segments]
        lines += [f"{t['name']}: closest {t['distance']:.1f} m at MD {t['closest_md']:.1f} m — "
                  + ("inside radius" if t["hit"] else "outside radius" if t["radius"] else "no radius given")
                  for t in result.targets]
        lines += [f"WARNING: {w}" for w in result.warnings]
        self.summary_label.setText("\n".join(lines))
        self._plot(result.stations)
        self._set_result_actions(True)
        self._refresh_plan_actions()
        return result

    # -- M62 plots -------------------------------------------------------
    def _plot(self, stations) -> None:
        md = [s["md"] for s in stations]
        for key, widget in self.plot_widgets.items():
            widget.clear()
            if stations:
                widget.plot(md, [s[key] for s in stations], pen=pg.mkPen("#1f77b4", width=2))
        if "tvd" in self.plot_widgets:
            self.plot_widgets["tvd"].getPlotItem().invertY(True)

    def plot_series(self, key: str) -> list:
        """Y values currently drawn on the ``key`` plot (for tests and export)."""
        widget = self.plot_widgets.get(key)
        if widget is None:
            return []
        items = widget.getPlotItem().listDataItems()
        return list(items[0].yData) if items else []

    # -- M62 saved plans -------------------------------------------------
    def set_well(self, well_id: Optional[int]) -> None:
        if well_id != self.well_id:
            self.current_plan = None
            self.plan_status_label.setText("No saved plan open.")
        self.well_id = well_id
        self.refresh_plans()
        self.refresh_tie_ins()

    def _selected_wellbore(self) -> Optional[int]:
        """The tree's selected wellbore, only when it belongs to this panel's well (M70.7)."""
        from core.selection_manager import SelectionManager

        return SelectionManager().wellbore_for(self.well_id, db=self.db_manager)

    def _plans_available(self) -> bool:
        """Plan storage needs a full database manager (survey-only stubs lack sessions)."""
        return callable(getattr(self.db_manager, "session_scope", None))

    def refresh_plans(self) -> None:
        self.plan_combo.clear()
        if self._plans_available() and self.well_id:
            try:
                plans = dp.list_plans(self.db_manager, self.well_id)
            except Exception as exc:  # the survey viewer must keep working; the failure is shown and logged
                logger.error("Loading saved plans failed: %s", exc, exc_info=True)
                self.plan_status_label.setText(f"Saved plans could not be loaded: {exc}")
                plans = []
            for plan in plans:
                self.plan_combo.addItem(
                    f"{plan['name']} — rev {plan['revision']} ({plan['status']})", plan["id"])
        self._refresh_plan_actions()

    def _refresh_plan_actions(self) -> None:
        can_store = self._plans_available() and bool(self.well_id)
        designed = self.result is not None and self.result.ok
        has_selection = self.plan_combo.currentData() is not None
        self.open_plan_btn.setEnabled(can_store and has_selection)
        self.save_new_btn.setEnabled(can_store and designed)
        self.save_rev_btn.setEnabled(can_store and designed and self.current_plan is not None)
        self.clone_btn.setEnabled(can_store and self.current_plan is not None)
        self.archive_btn.setEnabled(can_store and self.current_plan is not None)
        self.compare_plan_btn.setEnabled(can_store and has_selection and self.current_plan is not None)

    def current_references(self) -> dict:
        """Declared plan references (M105); a survey tie-in supplies them and a contradiction is refused."""
        declared = {"azimuth_reference": self.plan_azref_combo.currentData() or None,
                    "depth_datum": self.plan_datum_edit.text().strip() or None}
        revision_id = self.tie_combo.currentData()
        if revision_id is None:
            return declared
        from core import survey_revisions as sr
        revision = sr.get_revision(self.db_manager, revision_id)
        if revision is None:
            raise ValueError(f"survey revision {revision_id} is not available")
        for key, value in declared.items():
            if value and value.lower() != str(revision[key] or "").lower():
                raise ValueError(f"the plan {key.replace('_', ' ')} {value!r} contradicts survey rev "
                                 f"{revision['revision']} ({revision[key]!r})")
        return {key: revision[key] or None for key in declared}

    def current_inputs(self) -> dict:
        segments, targets = self.gather()
        return dp.plan_inputs(segments, targets=targets, step=self.step_spin.value(),
                              dls_limit=self.dls_limit_spin.value() or None,
                              vs_azimuth=self.vs_azimuth_spin.value(), tie_in=self.tie_in(),
                              **self.current_references())

    def refresh_tie_ins(self) -> None:
        """Survey revisions of this well as tie-in choices (M72)."""
        from core import survey_revisions as sr

        wanted = self.tie_combo.currentData()
        self.tie_combo.blockSignals(True)
        self.tie_combo.clear()
        self.tie_combo.addItem("Surface (MD 0, vertical)", None)
        revisions = []
        if self._plans_available() and self.well_id:
            try:
                revisions = sr.list_revisions(self.db_manager, self.well_id)
            except Exception as exc:  # shown and logged; the surface tie-in stays available
                logger.error("Loading survey revisions failed: %s", exc, exc_info=True)
                self.plan_status_label.setText(f"Survey revisions could not be loaded: {exc}")
        for rev in revisions:
            last = rev["results"][-1]
            self.tie_combo.addItem(f"Survey rev {rev['revision']} — last station MD {last['md']:.2f} m, "
                                   f"inc {last['inc']:.2f}, {rev['azimuth_reference']} north, {rev['depth_datum']}",
                                   rev["id"])
        index = self.tie_combo.findData(wanted)
        self.tie_combo.setCurrentIndex(max(0, index))
        self.tie_combo.blockSignals(False)

    def tie_in(self) -> Optional[dict]:
        from core import survey_revisions as sr

        revision_id = self.tie_combo.currentData()
        if revision_id is None:
            return None
        revision = sr.get_revision(self.db_manager, revision_id)
        if revision is None or revision["well_id"] != self.well_id:
            raise ValueError(f"survey revision {revision_id} is not available for this well")
        return sr.tie_in_from_revision(revision)

    def _solver_mode_changed(self) -> None:
        mode = self.solver_mode_combo.currentData()
        for widget in (self.drop_spin, self.final_inc_spin, self.final_hold_spin):
            widget.setEnabled(mode == SOLVE_S)
        self.max_inc_spin.setEnabled(mode != SOLVE_FIRST)
        self.solve_btn.setText({SOLVE_FIRST: "Solve to first target", SOLVE_ALL: "Solve through all targets",
                                SOLVE_S: "Solve S-profile"}[mode])

    def solve_to_target(self) -> Optional[dict]:
        """Fill the segments from the closed-form solver; the user still designs and saves explicitly."""
        from core.well_plan_designer import solve_build_hold

        if self.solver_mode_combo.currentData() != SOLVE_FIRST:
            return self._solve_m106()

        try:
            _segments, targets = self.gather()
            tie_in = self.tie_in()
        except ValueError as exc:
            self.summary_label.setText(f"Not solved: {exc}.")
            return None
        if not targets:
            self.summary_label.setText("Not solved: add a target first.")
            return None
        answer = solve_build_hold(targets[0], kop_md=self.kop_spin.value(), dls=self.build_spin.value(),
                                  tie_in=tie_in)
        if not answer["feasible"]:
            self.summary_label.setText(f"Not solved [{answer.get('code', '')}]: {answer['reason']}")
            return answer
        self.segment_table.setRowCount(0)
        for seg in answer["segments"]:
            self.add_segment(seg["type"], seg.get("length"), seg.get("inc"), seg.get("azi"), seg.get("dls"))
        self.design()
        self.summary_label.setText(
            self.summary_label.text() + f"\nSolved ({answer['method']}): hold {answer['inc']:.3f} deg at azimuth "
            f"{answer['azi']:.3f} deg, dogleg {answer['dogleg_deg']:.3f} deg, tangent {answer['hold_length']:.2f} m.")
        return answer

    def _solve_m106(self) -> Optional[dict]:
        """M106: multi-target or S-profile; verified by the canonical engine before the segments are filled."""
        from core import well_plan_designer as wpd

        try:
            _segments, targets = self.gather()
            tie_in = self.tie_in()
        except ValueError as exc:
            self.summary_label.setText(f"Not solved: {exc}.")
            return None
        if not targets:
            self.summary_label.setText("Not solved: add a target first.")
            return None
        limit = self.dls_limit_spin.value() or None
        if self.solver_mode_combo.currentData() == SOLVE_ALL:
            answer = wpd.solve_multi_target(targets, kop_md=self.kop_spin.value(), dls=self.build_spin.value(),
                                            tie_in=tie_in, max_inc=self.max_inc_spin.value(), dls_limit=limit,
                                            step=self.step_spin.value())
        else:
            answer = wpd.solve_s_profile(targets[0], kop_md=self.kop_spin.value(), build_dls=self.build_spin.value(),
                                         drop_dls=self.drop_spin.value(), final_inc=self.final_inc_spin.value(),
                                         final_hold=self.final_hold_spin.value(), tie_in=tie_in,
                                         max_inc=self.max_inc_spin.value(), dls_limit=limit,
                                         step=self.step_spin.value())
        if not answer["feasible"]:
            self.summary_label.setText(f"Not solved [{answer.get('code', '')}]: {answer['reason']}")
            return answer
        self.segment_table.setRowCount(0)
        for seg in answer["segments"]:
            self.add_segment(seg["type"], seg.get("length"), seg.get("inc"), seg.get("azi"), seg.get("dls"))
        self.design()
        misses = ", ".join(f"{row['name']} {row['distance']:.4f} m" for row in answer["verification"]["targets"])
        self.summary_label.setText(
            self.summary_label.text() + f"\nSolved ({answer['method']}): {len(answer['segments'])} segment(s), "
            f"TD {answer['td_md']:.2f} m MD; verified misses {misses} (tolerance "
            f"{answer['verification']['tolerance_m']} m). One feasible profile, not an optimum.")
        return answer

    def _show_plan(self, plan: dict, verb: str) -> None:
        self.current_plan = plan
        self.plan_status_label.setText(
            f"{verb} {plan['name']} rev {plan['revision']} ({plan['status']}) — {plan['method_version']}"
            + (f"; parent revision id {plan['parent_id']}" if plan.get("parent_id") else "")
            + f"; {dp.reference_text(plan)}")
        self.refresh_plans()
        index = self.plan_combo.findData(plan["id"])
        if index >= 0:
            self.plan_combo.setCurrentIndex(index)

    def save_new_plan(self, name: str) -> Optional[dict]:
        if self.design() is None or not self.result.ok:
            return None
        plan = dp.save_plan(self.db_manager, well_id=self.well_id, name=name, inputs=self.current_inputs(),
                            result=self.result, wellbore_id=self._selected_wellbore())
        self._show_plan(plan, "Saved")
        return plan

    def save_revision(self, note: str = "") -> Optional[dict]:
        if self.current_plan is None or self.design() is None or not self.result.ok:
            return None
        plan = dp.revise_plan(self.db_manager, self.current_plan["id"], self.current_inputs(), note=note)
        self._show_plan(plan, "Saved revision of")
        return plan

    def open_plan(self, revision_id: int) -> dict:
        plan = dp.get_plan(self.db_manager, revision_id)
        inputs = plan["inputs"]
        self.segment_table.setRowCount(0)
        for seg in inputs.get("segments", []):
            self.add_segment(seg["type"], seg.get("length", seg.get("tvd")), seg.get("inc"), seg.get("azi"),
                             seg.get("dls"))
        self.target_table.setRowCount(0)
        for target in inputs.get("targets", []):
            self.add_target(target.get("name", "Target"), target["north"], target["east"], target["tvd"],
                            target.get("radius"))
        self.step_spin.setValue(float(inputs.get("step", 30.0)))
        self.dls_limit_spin.setValue(float(inputs.get("dls_limit") or 0.0))
        self.vs_azimuth_spin.setValue(float(inputs.get("vs_azimuth", 0.0)))
        refs = dp.plan_references(plan)
        self.plan_azref_combo.setCurrentIndex(max(0, self.plan_azref_combo.findData(refs["azimuth_reference"] or "")))
        self.plan_datum_edit.setText(refs["depth_datum"] or "")
        self.refresh_tie_ins()
        pinned = (inputs.get("tie_in") or {}).get("survey_revision_id")
        index = self.tie_combo.findData(pinned) if pinned else 0
        if index < 0:                   # never redesign a pinned plan from another tie-in
            self.result = None
            self.summary_label.setText(f"Not designed: the plan's survey revision {pinned} is not available.")
            self._show_plan(plan, "Opened")
            return plan
        self.tie_combo.setCurrentIndex(index)
        self.design()
        if plan["method_version"] != PLAN_VERSION:
            self.summary_label.setText(
                self.summary_label.text() + f"\nNOTE: saved with {plan['method_version']}; redesigned with "
                f"{PLAN_VERSION}. The stored revision is unchanged.")
        self._show_plan(plan, "Opened")
        return plan

    def clone_plan(self, name: str) -> Optional[dict]:
        if self.current_plan is None:
            return None
        plan = dp.clone_plan(self.db_manager, self.current_plan["id"], name)
        self._show_plan(plan, "Cloned to")
        return plan

    def archive_plan(self) -> Optional[dict]:
        if self.current_plan is None:
            return None
        plan = dp.set_status(self.db_manager, self.current_plan["id"], "archived")
        self.current_plan = None
        self.refresh_plans()
        self.plan_status_label.setText(f"Archived {plan['name']} rev {plan['revision']}; it is kept read-only.")
        return plan

    def compare_with(self, revision_id: int) -> Optional[dict]:
        if self.current_plan is None:
            return None
        other = dp.get_plan(self.db_manager, revision_id)
        report = dp.compare_plans(self.current_plan, other)
        lines = [f"Compare {report['a']} vs {report['b']}"]
        lines += [f"input {d['input']}: {d['a']} → {d['b']}" for d in report["inputs"]] or ["inputs identical"]
        lines += [f"{r['quantity']}: {r['a']} → {r['b']}" + (f" (Δ {r['delta']:+.2f})" if r["delta"] is not None
                                                            else "") for r in report["results"]]
        self.plan_status_label.setText("\n".join(lines))
        return report

    def _plan_selection_changed(self, _index=0):
        self._refresh_plan_actions()

    def _open_clicked(self, _checked=False):
        if self.plan_combo.currentData() is not None:
            self.open_plan(self.plan_combo.currentData())

    def _guarded(self, action, *args):
        """Run a plan-library action; integrity/permission refusals are shown, not raised into Qt."""
        from core.authorization import AuthorizationError

        try:
            return action(*args)
        except (dp.PlanIntegrityError, LookupError, AuthorizationError) as exc:
            self.plan_status_label.setText(f"Not saved: {exc}")
            return None

    def _save_new_clicked(self, _checked=False):
        name, ok = QInputDialog.getText(self, "Save plan", "Plan name:")
        if ok and name.strip():
            self._guarded(self.save_new_plan, name.strip())

    def _save_revision_clicked(self, _checked=False):
        self._guarded(self.save_revision)

    def _clone_clicked(self, _checked=False):
        name, ok = QInputDialog.getText(self, "Clone plan", "New plan name:")
        if ok and name.strip():
            self._guarded(self.clone_plan, name.strip())

    def _archive_clicked(self, _checked=False):
        self._guarded(self.archive_plan)

    def _compare_clicked(self, _checked=False):
        if self.plan_combo.currentData() is not None:
            self.compare_with(self.plan_combo.currentData())

    def plan_rows(self) -> list:
        if self.result is None or not self.result.ok:
            return []
        return [{"md": s["md"], "inc": s["inc"], "azi": s["azi"]} for s in self.result.stations]

    def send_to_compare(self):
        rows = self.plan_rows()
        if not rows or (self.use_plan is None and not self.handover):
            return False
        source = f"Designed plan ({PLAN_VERSION})"
        try:
            tie_in = self.tie_in()
            self.handover_reference = self.current_references()
        except ValueError as exc:
            self.summary_label.setText(f"Not handed over: {exc}.")
            return False
        if tie_in:
            # M72: the planned path continues the pinned survey; positions must start at the tie-in station.
            from core import survey_revisions as sr
            revision = sr.get_revision(self.db_manager, tie_in["survey_revision_id"])
            above = [{"md": st["md"], "inc": st["inc"], "azi": st["azi"]}
                     for st in revision["stations"] if st["md"] < tie_in["md"] - 1e-6]
            rows = above + list(rows)
            source += f" tied to survey rev {revision['revision']} at MD {tie_in['md']:.2f} m"
        try:
            self.handover_targets = list(self.gather()[1])
        except ValueError as exc:
            self.handover_targets = []
            self.summary_label.setText(self.summary_label.text() + f"\nTargets not handed over ({exc}); "
                                       "the comparison runs without target checks.")
        if self.handover:
            self.plan_ready.emit(rows, source)
        if self.use_plan is not None:
            self.use_plan(rows, source)
        return True

    def _add_segment_clicked(self, _checked=False):
        self.add_segment()

    def _add_target_clicked(self, _checked=False):
        self.add_target()

    def _choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export designed plan", "designed_plan.csv", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def export_csv(self, path: str) -> bool:
        if self.result is None or not self.result.ok:
            return False
        try:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow([f"# {PLAN_VERSION}; {METHOD}; planning aid, not an approved plan"])
                for warning in self.result.warnings:
                    writer.writerow([f"# WARNING: {warning}"])
                writer.writerow(list(STATION_COLUMNS))
                for s in self.result.stations:
                    writer.writerow([f"{s[k]:.4f}" for k in ("md", "inc", "azi", "tvd", "north", "east", "vs", "dls")])
        except OSError as exc:
            logger.error("Plan export failed: %s", exc)
            self.summary_label.setText(f"Export failed: {exc}")
            return False
        return True
