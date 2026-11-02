"""M72: survey revisions of the selected well (Trajectory tab → "Survey revisions").

Freeze the current survey stations, or import a station file with a preview,
as an immutable revision; compare a revision with its parent. Nothing here
edits an existing revision.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from core import survey_revisions as sr

logger = logging.getLogger(__name__)
COLUMNS = ["Rev", "Mode", "Stations", "Last MD (m)", "Azimuth ref.", "Datum", "Source", "Parent", "Saved"]


class SurveyRevisionPanel(QWidget):
    revision_saved = Signal(int)

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.well_id: Optional[int] = None
        self.revisions: list = []
        self.pending: Optional[dict] = None          # a previewed import waiting for confirmation
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.datum_edit = QLineEdit()
        self.datum_edit.setPlaceholderText("e.g. RKB")
        self.azimuth_combo = QComboBox()
        for ref in sr.AZIMUTH_REFERENCES:
            self.azimuth_combo.addItem(ref, ref)
        self.unit_combo = QComboBox()
        for unit in sr.UNITS:
            self.unit_combo.addItem(unit, unit)
        self.mode_combo = QComboBox()
        for mode in ("replace", "append"):
            self.mode_combo.addItem(mode, mode)
        form.addRow("Depth datum", self.datum_edit)
        form.addRow("Azimuth reference", self.azimuth_combo)
        form.addRow("File MD unit", self.unit_combo)
        form.addRow("Import mode (when a revision exists)", self.mode_combo)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.freeze_btn = QPushButton("Freeze current survey")
        self.freeze_btn.clicked.connect(self.freeze_current)
        self.import_btn = QPushButton("Import station file…")
        self.import_btn.clicked.connect(self._choose_file)
        self.confirm_btn = QPushButton("Save previewed revision")
        self.confirm_btn.clicked.connect(self.confirm_import)
        self.compare_btn = QPushButton("Compare with parent")
        self.compare_btn.clicked.connect(self.compare_selected)
        for button in (self.freeze_btn, self.import_btn, self.confirm_btn, self.compare_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self.table)
        self.status = QLabel("Select a well.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(160)
        layout.addWidget(self.detail)
        self._update_actions()

    # ---- context -----------------------------------------------------------------------------
    def _available(self) -> bool:
        return callable(getattr(self.db_manager, "session_scope", None))

    def set_well(self, well_id: Optional[int]) -> None:
        if well_id != self.well_id:
            self.pending = None
            self.detail.clear()
        self.well_id = well_id or None
        self.refresh()

    def refresh(self) -> None:
        self.revisions = []
        if self._available() and self.well_id:
            try:
                self.revisions = sr.list_revisions(self.db_manager, self.well_id)
            except Exception as exc:  # shown and logged; the viewer keeps working
                logger.error("Loading survey revisions failed: %s", exc, exc_info=True)
                self.status.setText(f"Survey revisions could not be loaded: {exc}")
        self.table.setRowCount(len(self.revisions))
        for row, rev in enumerate(self.revisions):
            values = [rev["revision"], rev["mode"], rev["station_count"], f"{rev['stations'][-1]['md']:.2f}",
                      rev["azimuth_reference"], rev["depth_datum"], rev["source_type"],
                      next((p["revision"] for p in self.revisions if p["id"] == rev["parent_id"]), ""),
                      str(rev["created_at"])[:19]]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        if self.well_id and self._available():
            self.status.setText(f"{len(self.revisions)} survey revision(s). Saved revisions are never edited.")
        elif not self.well_id:
            self.status.setText("Select a well.")
        self._update_actions()

    def _update_actions(self) -> None:
        ready = self._available() and bool(self.well_id)
        self.freeze_btn.setEnabled(ready)
        self.import_btn.setEnabled(ready)
        self.confirm_btn.setEnabled(ready and self.pending is not None)
        selected = self.selected()
        self.compare_btn.setEnabled(bool(selected and selected.get("parent_id")))

    def selected(self) -> Optional[dict]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return self.revisions[rows[0]] if rows and rows[0] < len(self.revisions) else None

    def _user_id(self):
        from core.permissions import permissions
        return getattr(permissions, "user_id", None)

    def _wellbore(self):
        from core.selection_manager import SelectionManager
        return SelectionManager().wellbore_for(self.well_id, db=self.db_manager)

    def _done(self, rev: dict, verb: str) -> dict:
        self.refresh()
        notes = "; ".join(rev["warnings"]) or "no warnings"
        self.status.setText(f"{verb} survey revision {rev['revision']} ({rev['station_count']} stations, "
                            f"{rev['stations_sha256'][:12]}…). Checks: {notes}.")
        self.revision_saved.emit(rev["id"])
        return rev

    # ---- actions -----------------------------------------------------------------------------
    def freeze_current(self) -> Optional[dict]:
        try:
            rev = sr.snapshot_survey_points(self.db_manager, self.well_id, depth_datum=self.datum_edit.text(),
                                            azimuth_reference=self.azimuth_combo.currentData(),
                                            wellbore_id=self._wellbore(), user_id=self._user_id())
        except PermissionError:
            self.status.setText("Not saved: your role may not add survey revisions.")
            return None
        except sr.SurveyRevisionError as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        return self._done(rev, "Saved")

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Survey stations", "", "Station files (*.csv *.xlsx)")
        if path:
            self.preview_file(path)

    def preview_file(self, path: str) -> Optional[sr.SurveyPreview]:
        from core.trajectory_compare import PlanImportError, read_plan_file

        try:
            rows = read_plan_file(path, length_unit="m")       # values in file units; preview converts once
        except PlanImportError as exc:
            self.pending = None
            self.status.setText(f"Not read: {exc}")
            self._update_actions()
            return None
        checked = sr.preview(rows, source_unit=self.unit_combo.currentData(),
                             azimuth_reference=self.azimuth_combo.currentData(), depth_datum=self.datum_edit.text())
        lines = [f"Preview of {path.rsplit('/', 1)[-1]}: {len(checked.stations)} station(s) in metres."]
        lines += [f"ERROR: {e}" for e in checked.errors] + [f"warning: {w}" for w in checked.warnings]
        self.detail.setPlainText("\n".join(lines))
        self.pending = {"rows": rows, "path": path} if not checked.errors or self._append_ok(checked) else None
        self.status.setText("Review the preview, then save it as a revision." if self.pending
                            else "Not saved: fix the errors in the file first.")
        self._update_actions()
        return checked

    def _append_ok(self, checked) -> bool:
        return (self.revisions and self.mode_combo.currentData() == "append" and len(checked.stations) == 1
                and checked.errors == ["At least two valid stations are needed."])

    def confirm_import(self) -> Optional[dict]:
        if self.pending is None:
            return None
        latest = self.revisions[0] if self.revisions else None
        mode = self.mode_combo.currentData() if latest else "initial"
        try:
            rev = sr.save_revision(
                self.db_manager, self.well_id, self.pending["rows"], mode=mode,
                parent_id=latest["id"] if latest else None, wellbore_id=self._wellbore(),
                source_unit=self.unit_combo.currentData(), azimuth_reference=self.azimuth_combo.currentData(),
                depth_datum=self.datum_edit.text(), source_type="file",
                source_ref=self.pending["path"].rsplit("/", 1)[-1], user_id=self._user_id())
        except PermissionError:
            self.status.setText("Not saved: your role may not add survey revisions.")
            return None
        except sr.SurveyRevisionError as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.pending = None
        return self._done(rev, "Saved")

    def compare_selected(self) -> Optional[dict]:
        rev = self.selected()
        parent = next((p for p in self.revisions if rev and p["id"] == rev.get("parent_id")), None)
        if rev is None or parent is None:
            return None
        diff = sr.compare_revisions(parent, rev)
        if not diff["comparable"]:
            self.detail.setPlainText(diff["reason"])
            return diff
        lines = [f"Rev {parent['revision']} → rev {rev['revision']}: {diff['common']} common station(s), "
                 f"{len(diff['changed'])} changed, {len(diff['added'])} added, {len(diff['removed'])} removed "
                 "(MD/positions m, angles deg)."]
        for change in diff["changed"][:50]:
            lines.append(f"MD {change['md']:.2f}: " + ", ".join(
                f"{k} {v:+.4f}" for k, v in change.items() if k != "md"))
        self.detail.setPlainText("\n".join(lines))
        return diff
