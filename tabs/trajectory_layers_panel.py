"""M132: layer selection for the revision-aware 3D view (W6 Trajectory › 3D view).

The base is either the working survey (the DDR survey points the 2D views use - no revision identity, no declared
references, so nothing is overlaid on it), no survey (a plan drawn in its own tie-in frame) or an immutable survey
revision. Overlays (a second survey revision, a plan revision with its targets, an architecture revision) are
assembled by ``core.trajectory_layers`` in a background job (M103 runner) and drawn only when the stored records
prove they share the base frame; every layer that is not drawn, every component that is not placed and every
record excluded by the wellbore scope is listed with its reason.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core import trajectory_layers as tl
from core.context_jobs import CANCELLED, ERROR, STALE, ContextJobRunner, check_cancel
from tabs.job_retry import REFRESH_HINT, retry_button, scope_row, show_retry

logger = logging.getLogger(__name__)

WORKING, NO_SURVEY = "working", "none"
#: M138: with no well the panel says so; it never shows a blank frame or a working-survey state without a well
NO_WELL_TEXT = "NOT ASSESSED: select a well — no 3D layer is read or drawn."
STATUS_COLUMNS = ("Layer", "Record", "Status", "Reason")
WORKING_REASON = ("the working survey (DDR survey points) has no revision identity or declared references; select a "
                  "survey revision as the base to overlay records")

#: M138 working-survey row states besides DRAWN / NOT DRAWN / NOT SELECTED
NO_DATA, NOT_REPORTED = "NO DATA", "NOT REPORTED"


def _catalogue_job(db, params, cancel_event):
    check_cancel(cancel_event)
    return "catalogue", tl.catalogue(db, params["well"], params["wellbore"])


def _layers_job(db, params, cancel_event):
    check_cancel(cancel_event)
    return "layers", tl.build(db, params["well"], wellbore_id=params["wellbore"], survey_id=params["survey"],
                              compare_id=params["compare"], plan_id=params["plan"],
                              architecture_id=params["architecture"], unit=params["unit"])


class TrajectoryLayersPanel(QWidget):
    working_selected = Signal()          # the viewer draws its composed working-survey path
    layers_ready = Signal(object)        # LayerSet

    def __init__(self, db_manager=None, unit_getter: Optional[Callable[[], str]] = None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.unit_getter = unit_getter or (lambda: "m")
        self.well_id: Optional[int] = None
        self.wellbore_id: Optional[int] = None
        self.catalogue = {"surveys": [], "plans": [], "architectures": [], "excluded": []}
        self.layer_set: Optional[tl.LayerSet] = None
        self._pending = None                 # "catalogue" | "layers": what the running job reads
        self.working: Optional[tuple] = None  # M138: (stations, drawable) the viewer composed; None = not reported
        self.jobs = ContextJobRunner(None, "3D layers", refresh_hint=REFRESH_HINT, parent=self)
        self.jobs.result_ready.connect(self._job_result)
        self.jobs.state_changed.connect(self._job_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        grid = QGridLayout()
        self.base_combo, self.compare_combo = QComboBox(), QComboBox()
        self.plan_combo, self.architecture_combo = QComboBox(), QComboBox()
        for column, (label, combo) in enumerate((("Base", self.base_combo), ("Second survey", self.compare_combo),
                                                 ("Plan + targets", self.plan_combo),
                                                 ("Architecture", self.architecture_combo))):
            grid.addWidget(QLabel(label), 0, column)
            grid.addWidget(combo, 1, column)
            combo.setMinimumContentsLength(18)
            combo.currentIndexChanged.connect(self._choices_changed)
        layout.addLayout(grid)
        self.frame_label = QLabel(NO_WELL_TEXT)
        self.frame_label.setWordWrap(True)
        self.retry_btn = retry_button(self._retry)
        layout.addLayout(scope_row(self.frame_label, self.retry_btn))
        self.status_table = QTableWidget(0, len(STATUS_COLUMNS))
        self.status_table.setHorizontalHeaderLabels(STATUS_COLUMNS)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.status_table.setMaximumHeight(150)
        layout.addWidget(self.status_table)
        self._fill_combos()

    # -- scope ------------------------------------------------------------------------------------------------
    def set_scope(self, well_id: Optional[int], wellbore_id: Optional[int] = None) -> Optional[int]:
        """New well / wellbore: back to the working survey; the selectable records are read in the background."""
        self.well_id, self.wellbore_id = well_id or None, wellbore_id or None
        self.catalogue = {"surveys": [], "plans": [], "architectures": [], "excluded": []}
        self.layer_set = None
        self._fill_combos()
        if self.well_id is None:
            self.jobs.invalidate()
            self._show_no_well()
            return None
        if self.db_manager is None:
            self.jobs.invalidate()
            self._show_working()
            return None
        self.jobs.db_manager = self.db_manager
        self._pending = "catalogue"
        return self.jobs.start(_catalogue_job, {"well": self.well_id, "wellbore": self.wellbore_id})

    def _fill_combos(self) -> None:
        def fill(combo, first, records, extra=()):
            combo.blockSignals(True)
            combo.clear()
            for label, data in ((first[0], first[1]),) + tuple(extra):
                combo.addItem(label, data)
            for record in records:
                combo.addItem(record["label"], record["id"])
            combo.setCurrentIndex(0)
            combo.blockSignals(False)

        fill(self.base_combo, ("Working survey (DDR survey points — not a revision)", WORKING),
             self.catalogue["surveys"], extra=(("No survey (plan in its own tie-in frame)", NO_SURVEY),))
        fill(self.compare_combo, ("None", None), self.catalogue["surveys"])
        fill(self.plan_combo, ("None", None), self.catalogue["plans"])
        fill(self.architecture_combo, ("None", None), self.catalogue["architectures"])

    def choices(self) -> dict:
        return {"base": self.base_combo.currentData(), "compare": self.compare_combo.currentData(),
                "plan": self.plan_combo.currentData(), "architecture": self.architecture_combo.currentData()}

    def select(self, *, base=None, compare=None, plan=None, architecture=None) -> Optional[int]:
        """Pick records by id (tests and drill-down); one layer build for the whole choice."""
        for combo, value in ((self.compare_combo, compare), (self.plan_combo, plan),
                             (self.architecture_combo, architecture), (self.base_combo, base)):
            index = combo.findData(value) if value is not None else 0
            combo.blockSignals(True)
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)
        return self._choices_changed()

    def _choices_changed(self, *_args) -> Optional[int]:
        choice = self.choices()
        if self.well_id is None or self.db_manager is None or choice["base"] == WORKING:
            self.jobs.invalidate()
            self._show_working()
            return None
        self.jobs.db_manager = self.db_manager
        self._pending = "layers"
        return self.jobs.start(_layers_job, {
            "well": self.well_id, "wellbore": self.wellbore_id,
            "survey": None if choice["base"] == NO_SURVEY else choice["base"], "compare": choice["compare"],
            "plan": choice["plan"], "architecture": choice["architecture"], "unit": self.unit_getter()})

    def refresh(self) -> Optional[int]:
        """Unit or scale changed: rebuild the current choice (the working survey is redrawn by the viewer)."""
        return self._choices_changed()

    def _retry(self, _checked: bool = False) -> Optional[int]:
        """M138: Retry re-reads what failed for the current scope: the record list, or the chosen layers."""
        if self._pending == "catalogue":
            return self.set_scope(self.well_id, self.wellbore_id)
        return self._choices_changed()

    def wait(self, timeout_ms: int = 30000) -> bool:
        return self.jobs.wait(timeout_ms)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return self.jobs.shutdown(timeout_ms)

    # -- results ------------------------------------------------------------------------------------------------
    def _job_state(self, state: str, message: str) -> None:
        show_retry(self.retry_btn, state)
        if state not in (ERROR, STALE, CANCELLED):
            return
        self.layer_set = None
        if self._pending == "catalogue":
            # The revision records could not be listed: the working survey stays, and the panel says why.
            self._show_working()
            self.frame_label.setText(f"Revision records: {message} The working survey is shown.")
            return
        self.frame_label.setText(message)
        self.status_table.setRowCount(0)
        self.layers_ready.emit(None)

    def _job_result(self, _job_id: int, result) -> None:
        kind, payload = result
        if kind == "catalogue":
            self.catalogue = payload
            self._fill_combos()
            self._show_working()
            return
        self.layer_set = payload
        self.frame_label.setText(f"{payload.frame_label}. {payload.label}. {payload.method}. {payload.scope_label}.")
        rows = [(layer.label, layer.source, layer.status, layer.reason) for layer in payload.layers]
        for layer in payload.layers:
            rows.extend((f"  {name}", layer.source, "NOT PLACED", why) for name, why in layer.not_placed)
        rows.extend(("Excluded", source, "EXCLUDED (scope)", why) for source, why in payload.excluded)
        self._fill_status(rows)
        self.layers_ready.emit(payload)

    def set_working_state(self, stations: Optional[int], drawable: bool = False) -> None:
        """M138: what the viewer composed from the DDR survey points of its scope, so the working-survey row
        never says DRAWN for a scope without stations. ``None``: not known (the stations could not be read)."""
        self.working = None if stations is None else (int(stations), bool(drawable))
        if self.layer_set is None and self.choices()["base"] == WORKING:
            self._fill_status(self._working_rows())

    def _working_status(self) -> tuple:
        if not self.well_id:
            return tl.NOT_SELECTED, "select a well"
        if self.working is None:
            return NOT_REPORTED, "the trajectory view has not reported what it composed from the DDR survey points"
        stations, drawable = self.working
        if not stations:
            return NO_DATA, "no DDR survey point is recorded in the trajectory view's scope; nothing is drawn"
        if not drawable:
            return tl.NOT_DRAWN, f"{stations} station(s), not drawable (the 2D views say why)"
        return tl.DRAWN, f"{stations} station(s) composed by the trajectory engine as in the 2D views"

    def _working_rows(self) -> list:
        choice = self.choices()
        selected = [(label, choice[key]) for key, label in (("compare", "Second survey revision"),
                                                            ("plan", "Plan revision"),
                                                            ("architecture", "Architecture revision"))
                    if choice[key] is not None]
        rows = [("Working survey", "DDR survey points") + self._working_status()]
        rows.extend((label, f"#{record}", tl.NOT_DRAWN, WORKING_REASON) for label, record in selected)
        rows.extend(("Excluded", source, "EXCLUDED (scope)", why) for source, why in self.catalogue["excluded"])
        return rows

    def _show_no_well(self) -> None:
        self.layer_set = None
        self._fill_status([])
        self.frame_label.setText(NO_WELL_TEXT)
        self.working_selected.emit()          # the host clears any layer drawn for the previous well

    def _show_working(self) -> None:
        self.layer_set = None
        self._fill_status(self._working_rows())
        self.frame_label.setText("Base: the working survey. " + tl.LAYER_LABEL + ".")
        self.working_selected.emit()

    def _fill_status(self, rows) -> None:
        self.status_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self.status_table.setItem(i, j, item)
