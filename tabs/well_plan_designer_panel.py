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
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.well_plan_designer import METHOD, PLAN_VERSION, design_plan

logger = logging.getLogger(__name__)

SEGMENT_TYPES = (("hold", "Vertical / hold (length m)"), ("curve", "Build / drop / turn (inc, azi, DLS)"),
                 ("hold_to_tvd", "Hold to TVD (m)"))
STATION_COLUMNS = ("MD (m)", "Inc (deg)", "Azi (deg)", "TVD (m)", "North (m)", "East (m)", "VS (m)", "DLS (deg/30m)")


class WellPlanDesignerPanel(QWidget):
    """Plan designer.  The designed stations are handed over through ``plan_ready``
    (Qt signal: no Python reference back to the receiver, so an embedding viewer is
    freed deterministically - see tests/test_m50_trajectory_3d_disposal.py) and/or a
    standalone ``use_plan`` callable."""

    plan_ready = Signal(list, str)

    def __init__(self, parent=None, use_plan: Optional[Callable[[list, str], None]] = None,
                 handover: bool = False):
        super().__init__(parent)
        self.use_plan = use_plan
        self.handover = bool(handover)
        self.result = None
        layout = QVBoxLayout(self)

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
        layout.addWidget(self.station_table, 1)
        self._set_result_actions(False)

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
        result = design_plan(segments, step=self.step_spin.value(), dls_limit=limit,
                             vs_azimuth=self.vs_azimuth_spin.value(), targets=targets)
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
        self._set_result_actions(True)
        return result

    def plan_rows(self) -> list:
        if self.result is None or not self.result.ok:
            return []
        return [{"md": s["md"], "inc": s["inc"], "azi": s["azi"]} for s in self.result.stations]

    def send_to_compare(self):
        rows = self.plan_rows()
        if not rows or (self.use_plan is None and not self.handover):
            return False
        source = f"Designed plan ({PLAN_VERSION})"
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
