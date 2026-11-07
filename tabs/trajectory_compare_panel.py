"""Trajectory comparison / clearance SCREENING panel (M52, inside the trajectory viewer).

* Plan vs actual of the selected well (plan from CSV/XLSX, MD unit stated by the
  user) or centre-to-centre separation from an offset well.
* All numbers come from ``core.trajectory_compare``; the panel only gathers
  plain inputs, runs the comparison on a worker and presents the result.
  Survey/well reads are small single queries and run on the GUI thread, like the
  viewer's own reads; the CPU work (closest approach) runs on a FunctionWorker
  whose late results are dropped by a token.
* Every result shows ``LABEL``: screening only, no ISCWSA uncertainty, not
  approved.  NOT ASSESSED lists every missing input; nothing is guessed.
* "Save" inserts a NEW calculation record (never overwrites) holding the method version and every input
  station (M108), so History can re-run and verify it; "Export CSV"
  writes the shown rows with the label and method in the header.
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core import trajectory_compare as tc
from core.async_workers import FunctionWorker, release_when_finished

logger = logging.getLogger(__name__)

PLAN_COLUMNS = (("actual_md", "Actual MD (m)"), ("plan_md", "Plan MD (m)"), ("distance_m", "Distance (m)"),
                ("high_m", "High(+)/Low(-) (m)"), ("right_m", "Right(+)/Left(-) (m)"), ("along_m", "Along (m)"),
                ("note", "Note"))
OFFSET_COLUMNS = (("reference_md", "Reference MD (m)"), ("offset_md", "Offset MD (m)"),
                  ("distance_m", "Centre-to-centre (m)"))


def _selection():
    """The application's SelectionManager (M124), or None where it cannot be created."""
    try:
        from core.selection_manager import SelectionManager
        return SelectionManager()
    except Exception as exc:  # silent-ok: a panel without the global selection checks its local token only
        logger.debug("Selection manager unavailable: %s", type(exc).__name__)
        return None


def _compute(inputs: dict):
    """Worker body: plain dicts in, a Comparison out (no Qt, no ORM). M108: the same function re-runs a
    stored record, so it lives in ``core.trajectory_compare``."""
    return tc.run_comparison(inputs)


target_checks = tc.target_checks     # M72 helper, moved to the core in M108 (kept for callers)


class TrajectoryComparePanel(QWidget):
    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.well_id: Optional[int] = None
        self.plan_rows: Optional[list] = None
        self.plan_reference: dict = {}          # M105: what the plan declares (empty = NOT DECLARED)
        self.plan_source = ""
        self.plan_targets: list = []
        self.result: Optional[tc.Comparison] = None
        self.last_inputs: Optional[dict] = None
        self.saved_ids: list = []
        self._token = 0                         # local: a newer comparison or a cleared result (same context)
        self._run_ticket = None                 # M124: central identity the running comparison was started for
        self._worker = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.label_banner = QLabel(tc.LABEL)
        self.label_banner.setStyleSheet("background:#fff4e0;color:#9a5b00;font-weight:bold;padding:6px;")
        self.label_banner.setWordWrap(True)
        layout.addWidget(self.label_banner)

        row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Plan vs actual (this well)", "plan")
        self.mode_combo.addItem("Offset well (centre-to-centre)", "offset")
        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(1.0, 100.0)
        self.step_spin.setValue(tc.DEFAULT_STEP_M)
        self.step_spin.setSuffix(" m")
        self.run_button = QPushButton("Compare")
        for widget in (QLabel("Mode:"), self.mode_combo, QLabel("Sample step:"), self.step_spin):
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(self.run_button)
        layout.addLayout(row)

        plan_row = QHBoxLayout()
        self.plan_button = QPushButton("Load plan (CSV/XLSX)...")
        self.plan_unit_combo = QComboBox()
        self.plan_unit_combo.addItem("Plan MD in metres", "m")
        self.plan_unit_combo.addItem("Plan MD in feet", "ft")
        self.plan_label = QLabel("No plan loaded")
        for widget in (self.plan_button, self.plan_unit_combo, self.plan_label):
            plan_row.addWidget(widget)
        plan_row.addStretch()
        self.plan_widget = QWidget()
        self.plan_widget.setLayout(plan_row)
        layout.addWidget(self.plan_widget)

        actual_row = QHBoxLayout()
        self.actual_combo = QComboBox()
        self.actual_combo.addItem("Live survey points (not a revision)", None)
        self.actual_combo.currentIndexChanged.connect(lambda _i: self._clear_result("Actual survey changed; compare again."))
        actual_row.addWidget(QLabel("Actual survey:"))
        actual_row.addWidget(self.actual_combo, 1)
        layout.addLayout(actual_row)

        offset_box = QVBoxLayout()
        offset_box.setContentsMargins(0, 0, 0, 0)
        offset_row = QHBoxLayout()
        self.offset_combo = QComboBox()
        self.crs_check = QCheckBox("Both wellheads (northing/easting) are in the same projected CRS, metres")
        offset_row.addWidget(QLabel("Offset well:"))
        offset_row.addWidget(self.offset_combo, 1)
        offset_row.addWidget(self.crs_check)
        offset_box.addLayout(offset_row)
        offset_rev_row = QHBoxLayout()            # M129: the offset survey is a declared survey revision
        self.offset_rev_combo = QComboBox()
        offset_rev_row.addWidget(QLabel("Offset survey:"))
        offset_rev_row.addWidget(self.offset_rev_combo, 1)
        offset_box.addLayout(offset_rev_row)
        self.offset_widget = QWidget()
        self.offset_widget.setLayout(offset_box)
        self.offset_combo.currentIndexChanged.connect(self._refresh_offset_revisions)
        self.offset_rev_combo.currentIndexChanged.connect(
            lambda _i: self._clear_result("Offset survey changed; compare again."))
        layout.addWidget(self.offset_widget)

        self.status_label = QLabel("Select a well, then compare.")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)
        self.reason_list = QListWidget()
        self.reason_list.setMaximumHeight(110)
        self.reason_list.setWordWrap(True)
        layout.addWidget(self.reason_list)
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Save as new calculation record")
        self.export_button = QPushButton("Export CSV...")
        self.save_button.setEnabled(False)
        self.export_button.setEnabled(False)
        actions.addStretch()
        actions.addWidget(self.save_button)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)

        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.plan_button.clicked.connect(self._choose_plan)
        self.run_button.clicked.connect(self.run)
        self.save_button.clicked.connect(lambda: self.save())
        self.export_button.clicked.connect(self._choose_export)
        self._mode_changed()

    @property
    def mode(self) -> str:
        return self.mode_combo.currentData()

    def _mode_changed(self):
        self.plan_widget.setVisible(self.mode == "plan")
        self.offset_widget.setVisible(self.mode == "offset")
        self._clear_result("Mode changed; compare again.")

    def refresh_actual_sources(self) -> None:
        """Live survey points, or an immutable survey revision of this well (M72)."""
        from core import survey_revisions as sr

        self.actual_combo.clear()
        self.actual_combo.addItem("Live survey points (not a revision)", None)
        if callable(getattr(self.db_manager, "session_scope", None)) and self.well_id:
            try:
                for rev in sr.list_revisions(self.db_manager, self.well_id):
                    self.actual_combo.addItem(f"Survey revision {rev['revision']} ({rev['station_count']} stations, "
                                              f"{rev['azimuth_reference']} north, {rev['depth_datum']})", rev["id"])
            except Exception as exc:                    # read error is a state, not an empty list
                logger.warning("Survey revisions could not be read: %s", type(exc).__name__)
                self.actual_combo.addItem("(survey revisions could not be read)", None)

    def set_well(self, well_id: Optional[int]):
        self.well_id = well_id
        self.refresh_actual_sources()
        self.offset_combo.clear()
        if self.db_manager is not None:
            try:
                for wid, name in tc.list_wells(self.db_manager):
                    if wid != well_id:
                        self.offset_combo.addItem(name, wid)
            except Exception as exc:                    # read error is a state, not an empty list
                logger.warning("Offset well list could not be read: %s", type(exc).__name__)
                self.offset_combo.addItem("(well list could not be read)", None)
        self._refresh_offset_revisions()
        self._clear_result("Select a well, then compare." if not well_id else "Ready to compare.")

    def _refresh_offset_revisions(self, *_args) -> None:
        """M129: survey revisions of the offset well (newest first); live points declare no references."""
        from core import survey_revisions as sr

        self.offset_rev_combo.blockSignals(True)
        try:
            self.offset_rev_combo.clear()
            offset_id = self.offset_combo.currentData()
            if offset_id and callable(getattr(self.db_manager, "session_scope", None)):
                try:
                    for rev in sr.list_revisions(self.db_manager, int(offset_id)):
                        self.offset_rev_combo.addItem(
                            f"Survey revision {rev['revision']} ({rev['station_count']} stations, "
                            f"{rev['azimuth_reference']} north, {rev['depth_datum']})", rev["id"])
                except Exception as exc:                # read error is a state, not an empty list
                    logger.warning("Offset survey revisions could not be read: %s", type(exc).__name__)
                    self.offset_rev_combo.clear()
                    self.offset_rev_combo.addItem("(survey revisions could not be read)", None)
            if self.offset_rev_combo.count() == 0:
                self.offset_rev_combo.addItem("Live survey points (not a revision: no declared azimuth reference "
                                              "or datum)", None)
        finally:
            self.offset_rev_combo.blockSignals(False)
        self._clear_result("Offset well changed; compare again.")

    # ------------------------------------------------------------ plan file
    def _choose_plan(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load trajectory plan", "",
                                              "Plan tables (*.csv *.txt *.xlsx *.xlsm)")
        if path:
            self.load_plan(path)

    def load_plan(self, path: str) -> bool:
        try:
            rows, reference = tc.read_plan_file_with_reference(path, length_unit=self.plan_unit_combo.currentData())
        except tc.PlanImportError as exc:
            self.plan_rows, self.plan_source = None, ""
            self.plan_label.setText(f"Plan refused: {exc}")
            return False
        except (OSError, ValueError) as exc:
            self.plan_rows, self.plan_source = None, ""
            self.plan_label.setText(f"Plan could not be read ({type(exc).__name__})")
            return False
        self.plan_rows, self.plan_source = rows, os.path.basename(path)
        self.plan_targets = []
        self.plan_reference = reference
        self.plan_label.setText(f"{self.plan_source}: {len(rows)} stations "
                                f"(MD {self.plan_unit_combo.currentData()} -> m; {self._reference_label()})")
        self._clear_result("Plan loaded; compare again.")
        return True

    def _reference_label(self) -> str:
        ref = self.plan_reference or {}
        return ", ".join(f"{key.replace('_', ' ')} {ref.get(key) or 'NOT DECLARED'}" for key in tc.REFERENCE_KEYS)

    def set_plan_rows(self, rows, source: str, targets=None, reference=None) -> bool:
        """Use plan stations handed over in memory (M55 plan designer; MD in metres)."""
        try:
            stations = [{"md": float(r["md"]), "inc": float(r["inc"]), "azi": float(r["azi"])}
                        for r in rows or ()]
        except (KeyError, TypeError, ValueError):  # silent-ok: unreadable plan is refused below with a visible message
            stations = []
        if len(stations) < 2:
            self.plan_rows, self.plan_source = None, ""
            self.plan_label.setText("Plan refused: fewer than two readable stations were supplied")
            return False
        self.plan_rows, self.plan_source = stations, str(source)
        self.plan_targets = [dict(t) for t in targets or ()]
        self.plan_reference = {k: (reference or {}).get(k) for k in tc.REFERENCE_KEYS}
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("plan"))
        self.plan_label.setText(f"{self.plan_source}: {len(stations)} stations (MD m, in memory; "
                                f"{self._reference_label()})")
        self._clear_result("Plan loaded; compare again.")
        return True

    # ------------------------------------------------------------- compare
    def _gather(self) -> Optional[dict]:
        if not self.well_id or self.db_manager is None:
            self._clear_result("Select a well first.")
            return None
        inputs = {"mode": self.mode, "step": float(self.step_spin.value()), "well_id": self.well_id}
        try:
            revision_id = self.actual_combo.currentData()
            if revision_id is not None:
                from core import survey_revisions as sr
                revision = sr.get_revision(self.db_manager, revision_id)
                if revision is None or revision["well_id"] != self.well_id:
                    self._clear_result("The selected survey revision is not available for this well.")
                    return None
                try:
                    sr.verify_for_use(revision, "a trajectory comparison")
                except sr.SurveyRevisionError as exc:
                    self._clear_result(f"Not compared: {exc}")
                    return None
                actual_reference = {k: revision.get(k) for k in tc.REFERENCE_KEYS}
                inputs["actual_rows"] = [dict(st) for st in revision["stations"]]
                inputs["actual_survey_revision_id"] = revision["id"]
                inputs["actual_survey_sha256"] = revision["stations_sha256"]
            else:
                actual_reference = {}               # legacy survey points declare no reference
                inputs["actual_rows"] = [{"md": r["md"], "inc": r["inc"], "azi": r["azi"]}
                                         for r in self.db_manager.load_survey_points(well_id=self.well_id)]
            if self.mode == "plan":
                if not self.plan_rows:
                    self._clear_result("Load a plan file first.")
                    return None
                check = tc.reference_check(self.plan_reference, actual_reference)
                if not check["ok"]:
                    self._clear_result(check["summary"])
                    return None
                inputs["reference_check"] = check["summary"]
                inputs["plan_rows"] = list(self.plan_rows)
                inputs["plan_source"] = self.plan_source
                inputs["targets"] = list(self.plan_targets)
            else:
                offset_id = self.offset_combo.currentData()
                if not offset_id:
                    self._clear_result("Select an offset well.")
                    return None
                inputs["offset_well_id"] = int(offset_id)
                offset_reference = {}
                offset_revision_id = self.offset_rev_combo.currentData()
                if offset_revision_id is not None:
                    from core import survey_revisions as sr
                    offset_revision = sr.get_revision(self.db_manager, offset_revision_id)
                    if offset_revision is None or offset_revision["well_id"] != int(offset_id):
                        self._clear_result("The selected offset survey revision is not available for that well.")
                        return None
                    try:
                        sr.verify_for_use(offset_revision, "a trajectory comparison")
                    except sr.SurveyRevisionError as exc:
                        self._clear_result(f"Not compared: {exc}")
                        return None
                    inputs["offset_rows"] = [dict(st) for st in offset_revision["stations"]]
                    inputs["offset_survey_revision_id"] = offset_revision["id"]
                    inputs["offset_survey_sha256"] = offset_revision["stations_sha256"]
                    offset_reference = {"survey_revision_id": offset_revision["id"],
                                        **{k: offset_revision.get(k) for k in tc.REFERENCE_KEYS}}
                else:                                   # legacy points: references undeclared -> NOT ASSESSED
                    inputs["offset_rows"] = [{"md": r["md"], "inc": r["inc"], "azi": r["azi"]}
                                             for r in self.db_manager.load_survey_points(well_id=int(offset_id))]
                actual_id = inputs.get("actual_survey_revision_id")
                inputs["references"] = {
                    "reference": {"survey_revision_id": actual_id, **actual_reference} if actual_id else {},
                    "offset": offset_reference}
                inputs["reference_well"] = tc.well_reference(self.db_manager, self.well_id)
                inputs["offset_well"] = tc.well_reference(self.db_manager, int(offset_id))
                inputs["same_crs"] = bool(self.crs_check.isChecked())
        except Exception as exc:
            logger.warning("Trajectory comparison inputs could not be read: %s", type(exc).__name__)
            self._clear_result(f"Survey or well data could not be read ({type(exc).__name__}); nothing compared.")
            return None
        return inputs

    def run(self):
        inputs = self._gather()
        if inputs is None:
            return
        self._clear_result("Comparing...")          # increments the token: older results are stale
        token = self._token
        selection = _selection()
        # M124 (D7): the comparison reads the well's surveys, so it depends on the selected well only.
        self._run_ticket = selection.ticket(("well_id",), local=token) if selection is not None else None
        self.last_inputs = inputs
        self.run_button.setEnabled(False)
        worker = FunctionWorker(_compute, inputs)
        self._worker = worker
        worker.result_ready.connect(lambda result, t=token: self._done(t, result))
        worker.failed.connect(lambda message, t=token: self._failed(t, message))
        worker.finished.connect(lambda w=worker: self._worker_finished(w))
        worker.start()
        release_when_finished(worker)

    def _worker_finished(self, worker):
        if self._worker is worker:
            self._worker = None
            self.run_button.setEnabled(True)

    def _central_change(self, token):
        """M124: why a comparison started under ``token`` must not be shown although no newer one ran."""
        ticket = self._run_ticket
        if ticket is None or ticket.local != token:
            return None
        return ticket.stale_reason(_selection(), token)

    def _failed(self, token, message):
        if token != self._token:
            return
        if self._central_change(token):
            self._clear_result("The selected well changed while comparing; nothing is shown. Compare again.")
            return
        logger.error("Trajectory comparison failed: %s", message.splitlines()[0] if message else "")
        self._clear_result("Comparison failed (verification failure); no result is shown.")

    def _done(self, token, result):
        if token != self._token:
            return                                       # a newer comparison was started
        if self._central_change(token):
            # M124 (D7): the app's selected well moved while the worker ran (the viewer may not have been
            # told yet: a hidden tab defers its handlers) - never show a comparison for another well.
            self._clear_result("The selected well changed while comparing; nothing is shown. Compare again.")
            return
        self.result = result
        self.reason_list.clear()
        for text in list(result.reasons) + list(result.warnings):
            self.reason_list.addItem(text)
        if result.status == tc.NOT_ASSESSED:
            self.status_label.setText(f"{tc.NOT_ASSESSED}: required inputs are missing (listed below). {tc.LABEL}")
            self._fill([], ())
            self.save_button.setEnabled(False)
            self.export_button.setEnabled(False)
            return
        closest = result.closest or {}
        if result.kind == "plan_vs_actual":
            for check in getattr(result, "target_checks", None) or []:
                if check["status"] != "ASSESSED":
                    self.reason_list.addItem(f"Target {check['name']}: NOT ASSESSED ({check['reason']}).")
                    continue
                verdict = ("no radius, hit not judged" if check["hit"] is None
                           else "inside radius" if check["hit"] else "outside radius")
                self.reason_list.addItem(
                    f"Target {check['name']}: actual path passes {check['distance_m']:.2f} m from the centre at "
                    f"MD {check['actual_md']:.2f} m ({verdict}). SCREENING.")
            self.status_label.setText(
                f"Largest miss from plan: {closest.get('distance_m')} m at actual MD {closest.get('actual_md')} m "
                f"(high {closest.get('high_m')} m, right {closest.get('right_m')} m). {tc.LABEL}")
            self._fill(result.rows, PLAN_COLUMNS)
        else:
            self.status_label.setText(
                f"Closest centre-to-centre approach: {closest.get('distance_m')} m at reference MD "
                f"{closest.get('reference_md')} m / offset MD {closest.get('offset_md')} m. {tc.LABEL}")
            self._fill(result.rows, OFFSET_COLUMNS)
        self.save_button.setEnabled(True)
        self.export_button.setEnabled(True)

    def _fill(self, rows, columns):
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([c[1] for c in columns])
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (key, _title) in enumerate(columns):
                value = row.get(key)
                item = QTableWidgetItem("" if value is None else str(value))
                if key != "note":
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)

    def _clear_result(self, message: str):
        self._token += 1                                 # any running comparison becomes stale
        self.result = None
        self.status_label.setText(message)
        self.reason_list.clear()
        self._fill([], ())
        self.save_button.setEnabled(False)
        self.export_button.setEnabled(False)

    # ------------------------------------------------------- save / export
    def save(self) -> Optional[int]:
        if self.result is None or self.result.status != tc.ASSESSED or not self.last_inputs:
            return None
        ticket = self._run_ticket
        if ticket is not None and ticket.stale_reason(_selection(), ticket.local):
            # M124: the result was computed for the well selected when it ran; never save it for another
            self._clear_result("The selected well changed since this comparison; nothing was saved. Compare again.")
            return None
        # M108: the station rows are stored with the record so it can be re-run and verified later
        inputs = {k: v for k, v in self.last_inputs.items()}
        inputs["actual_stations"] = len(self.last_inputs.get("actual_rows") or [])
        inputs["actual_source"] = ("survey revision" if self.last_inputs.get("actual_survey_revision_id")
                                   else "live survey points (not a revision)")
        if getattr(self.result, "target_checks", None):
            inputs["target_checks"] = self.result.target_checks
        if "plan_rows" in self.last_inputs:
            inputs["plan_stations"] = len(self.last_inputs["plan_rows"])
        if "offset_rows" in self.last_inputs:
            inputs["offset_stations"] = len(self.last_inputs["offset_rows"])
            inputs["offset_source"] = ("survey revision" if self.last_inputs.get("offset_survey_revision_id")
                                       else "live survey points (not a revision)")
        from core.permissions import permissions
        user_id = getattr(permissions, "user_id", None)
        try:
            record_id = tc.save_comparison(self.db_manager, self.well_id, self.result, inputs=inputs, user_id=user_id)
        except PermissionError:
            self.status_label.setText("Not saved: your role may not write calculation records.")
            return None
        except Exception as exc:
            logger.warning("Trajectory comparison could not be saved: %s", type(exc).__name__)
            self.status_label.setText(f"Not saved ({type(exc).__name__}).")
            return None
        self.saved_ids.append(record_id)
        self.status_label.setText(self.status_label.text() + f"  Saved as calculation #{record_id}.")
        return record_id

    def _choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export comparison", "trajectory_comparison.csv", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def export_csv(self, path: str) -> bool:
        if self.result is None or self.result.status != tc.ASSESSED:
            return False
        columns = PLAN_COLUMNS if self.result.kind == "plan_vs_actual" else OFFSET_COLUMNS
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([f"# {tc.LABEL}"])
            writer.writerow([f"# method: {tc.METHOD_VERSION}; units: m, deg"])
            writer.writerow([title for _key, title in columns])
            for row in self.result.rows:
                writer.writerow(["" if row.get(key) is None else row.get(key) for key, _title in columns])
        return True

    # ------------------------------------------------------------ lifecycle
    def wait_until_idle(self, timeout_ms: int = 30000) -> bool:
        from PySide6.QtCore import QCoreApplication, QElapsedTimer
        timer = QElapsedTimer()
        timer.start()
        while self._worker is not None and timer.elapsed() < timeout_ms:
            QCoreApplication.processEvents()
            if self._worker is not None:
                self._worker.wait(10)
        QCoreApplication.processEvents()
        return self._worker is None

    def cleanup(self):
        self._token += 1
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(30000)
