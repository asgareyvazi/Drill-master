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
* "Save" inserts a NEW calculation record (never overwrites); "Export CSV"
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
from core.well_trajectory import compose_well_trajectory

logger = logging.getLogger(__name__)

PLAN_COLUMNS = (("actual_md", "Actual MD (m)"), ("plan_md", "Plan MD (m)"), ("distance_m", "Distance (m)"),
                ("high_m", "High(+)/Low(-) (m)"), ("right_m", "Right(+)/Left(-) (m)"), ("along_m", "Along (m)"),
                ("note", "Note"))
OFFSET_COLUMNS = (("reference_md", "Reference MD (m)"), ("offset_md", "Offset MD (m)"),
                  ("distance_m", "Centre-to-centre (m)"))


def _compute(inputs: dict):
    """Worker body: plain dicts in, a Comparison out (no Qt, no ORM)."""
    actual = compose_well_trajectory(inputs["actual_rows"])
    if inputs["mode"] == "plan":
        return tc.compare_plan(actual, tc.compose_plan(inputs["plan_rows"]), step=inputs["step"])
    offset = compose_well_trajectory(inputs["offset_rows"])
    return tc.compare_wells(actual, inputs["reference_well"], offset, inputs["offset_well"],
                            same_crs_confirmed=inputs["same_crs"], step=inputs["step"])


class TrajectoryComparePanel(QWidget):
    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.well_id: Optional[int] = None
        self.plan_rows: Optional[list] = None
        self.plan_source = ""
        self.result: Optional[tc.Comparison] = None
        self.last_inputs: Optional[dict] = None
        self.saved_ids: list = []
        self._token = 0
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

        offset_row = QHBoxLayout()
        self.offset_combo = QComboBox()
        self.crs_check = QCheckBox("Both wellheads (northing/easting) are in the same projected CRS, metres")
        offset_row.addWidget(QLabel("Offset well:"))
        offset_row.addWidget(self.offset_combo, 1)
        offset_row.addWidget(self.crs_check)
        self.offset_widget = QWidget()
        self.offset_widget.setLayout(offset_row)
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

    def set_well(self, well_id: Optional[int]):
        self.well_id = well_id
        self.offset_combo.clear()
        if self.db_manager is not None:
            try:
                for wid, name in tc.list_wells(self.db_manager):
                    if wid != well_id:
                        self.offset_combo.addItem(name, wid)
            except Exception as exc:                    # read error is a state, not an empty list
                logger.warning("Offset well list could not be read: %s", type(exc).__name__)
                self.offset_combo.addItem("(well list could not be read)", None)
        self._clear_result("Select a well, then compare." if not well_id else "Ready to compare.")

    # ------------------------------------------------------------ plan file
    def _choose_plan(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load trajectory plan", "",
                                              "Plan tables (*.csv *.txt *.xlsx *.xlsm)")
        if path:
            self.load_plan(path)

    def load_plan(self, path: str) -> bool:
        try:
            rows = tc.read_plan_file(path, length_unit=self.plan_unit_combo.currentData())
        except tc.PlanImportError as exc:
            self.plan_rows, self.plan_source = None, ""
            self.plan_label.setText(f"Plan refused: {exc}")
            return False
        except (OSError, ValueError) as exc:
            self.plan_rows, self.plan_source = None, ""
            self.plan_label.setText(f"Plan could not be read ({type(exc).__name__})")
            return False
        self.plan_rows, self.plan_source = rows, os.path.basename(path)
        self.plan_label.setText(f"{self.plan_source}: {len(rows)} stations "
                                f"(MD {self.plan_unit_combo.currentData()} -> m)")
        self._clear_result("Plan loaded; compare again.")
        return True

    # ------------------------------------------------------------- compare
    def _gather(self) -> Optional[dict]:
        if not self.well_id or self.db_manager is None:
            self._clear_result("Select a well first.")
            return None
        inputs = {"mode": self.mode, "step": float(self.step_spin.value()), "well_id": self.well_id}
        try:
            inputs["actual_rows"] = [{"md": r["md"], "inc": r["inc"], "azi": r["azi"]}
                                     for r in self.db_manager.load_survey_points(well_id=self.well_id)]
            if self.mode == "plan":
                if not self.plan_rows:
                    self._clear_result("Load a plan file first.")
                    return None
                inputs["plan_rows"] = list(self.plan_rows)
                inputs["plan_source"] = self.plan_source
            else:
                offset_id = self.offset_combo.currentData()
                if not offset_id:
                    self._clear_result("Select an offset well.")
                    return None
                inputs["offset_well_id"] = int(offset_id)
                inputs["offset_rows"] = [{"md": r["md"], "inc": r["inc"], "azi": r["azi"]}
                                         for r in self.db_manager.load_survey_points(well_id=int(offset_id))]
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

    def _failed(self, token, message):
        if token != self._token:
            return
        logger.error("Trajectory comparison failed: %s", message.splitlines()[0] if message else "")
        self._clear_result("Comparison failed (verification failure); no result is shown.")

    def _done(self, token, result):
        if token != self._token:
            return                                       # a newer comparison was started
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
        inputs = {k: v for k, v in self.last_inputs.items() if not k.endswith("_rows")}
        inputs["actual_stations"] = len(self.last_inputs.get("actual_rows") or [])
        if "plan_rows" in self.last_inputs:
            inputs["plan_stations"] = self.last_inputs["plan_rows"]
        if "offset_rows" in self.last_inputs:
            inputs["offset_stations"] = len(self.last_inputs["offset_rows"])
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
