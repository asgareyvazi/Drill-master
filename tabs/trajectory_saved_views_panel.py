"""M178/M179: saved views of the Well Trajectory Viewer (Trajectory tab → Well Trajectory Viewer → "Saved views").

The canonical replacement of the retired W6 "Trajectory Plot" save / load / export (M180). A saved view is named,
bound to the well, the selected wellbore of that well (when one is selected) and its source (the working survey
stations of the scope, or an immutable survey revision), and every change is a new immutable revision
(``core.trajectory_views``).  Open shows the stored snapshot and states whether the current data still produce it;
revise and archive refuse a view that another revision has superseded (optimistic concurrency).  Every failure
message says NOT SAVED; a success message is shown only after the database confirmed the revision.

Legacy "Trajectory Plot" rows (``trajectory_plots``) are listed read-only; they are never edited or deleted.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QListWidget, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from core import trajectory_views as tv

logger = logging.getLogger(__name__)
COLUMNS = ("Name", "Rev", "Status", "Source", "Stations", "Wellbore", "Saved (UTC)")
WORKING_SOURCE = 0


class TrajectorySavedViewsPanel(QWidget):
    """List, save, reopen, revise, clone, compare, archive / restore and export saved trajectory views."""

    view_opened = Signal(int)

    def __init__(self, db_manager=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        # The viewer pushes its state here (``set_viewer_context``); the panel keeps no reference to the viewer, so
        # no Python reference cycle ties the two widgets together (the M50 disposal rule).
        self.viewer_context = {"well_id": None, "report_id": None, "wellbore_id": None,
                               "settings": dict(tv.DEFAULT_SETTINGS)}
        self.well_id: Optional[int] = None
        self.views: list = []
        self.last_result: Optional[dict] = None
        self.last_compare: Optional[dict] = None
        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source for a new view or revision:"))
        self.source_combo = QComboBox()
        self.source_combo.setToolTip("Working survey stations of the viewer scope, or an immutable survey revision.")
        source_row.addWidget(self.source_combo, 1)
        self.archived_check = QCheckBox("Show archived")
        self.archived_check.toggled.connect(self.refresh)
        source_row.addWidget(self.archived_check)
        layout.addLayout(source_row)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._show_history)
        layout.addWidget(self.table, 2)
        buttons = QHBoxLayout()
        self.save_btn = QPushButton("Save current view…")
        self.open_btn = QPushButton("Open")
        self.revise_btn = QPushButton("Revise with current settings…")
        self.clone_btn = QPushButton("Clone…")
        self.compare_btn = QPushButton("Compare with previous revision")
        self.archive_btn = QPushButton("Archive…")
        self.restore_btn = QPushButton("Restore…")
        self.export_csv_btn = QPushButton("Export CSV…")
        self.export_json_btn = QPushButton("Export JSON…")
        for button, slot in ((self.save_btn, self.save_current), (self.open_btn, self.open_selected),
                             (self.revise_btn, self.revise_selected), (self.clone_btn, self.clone_selected),
                             (self.compare_btn, self.compare_selected), (self.archive_btn, self.archive_selected),
                             (self.restore_btn, self.restore_selected),
                             (self.export_csv_btn, self._export_csv),
                             (self.export_json_btn, self._export_json)):
            # bound methods, never lambdas over ``self``: a closure would tie the panel to its own buttons (M132)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.status = QLabel("Select a well to list its saved views.")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(140)
        layout.addWidget(self.details)
        history_box = QGroupBox("Revisions of the selected view")
        history_layout = QVBoxLayout(history_box)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(110)
        history_layout.addWidget(self.history_list)
        layout.addWidget(history_box)
        legacy_box = QGroupBox("Legacy 'Trajectory Plot' snapshots (read-only)")
        legacy_layout = QVBoxLayout(legacy_box)
        self.legacy_list = QListWidget()
        self.legacy_list.setMaximumHeight(90)
        self.legacy_list.setToolTip(tv.LEGACY_LABEL)
        legacy_layout.addWidget(self.legacy_list)
        layout.addWidget(legacy_box)
        self._update_buttons()

    # ------------------------------------------------------------------ context
    def _context(self) -> dict:
        return dict(self.viewer_context)

    def set_viewer_context(self, *, well_id, report_id, wellbore_id, settings) -> None:
        self.viewer_context = {"well_id": well_id, "report_id": report_id, "wellbore_id": wellbore_id,
                               "settings": dict(settings)}

    def set_well(self, well_id: Optional[int]) -> None:
        self.well_id = well_id
        self.refresh()

    def _fill_sources(self) -> None:
        from core import survey_revisions as sr

        current = self.source_combo.currentData()
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("Working survey stations (viewer scope)", WORKING_SOURCE)
        if self.well_id and self.db_manager is not None:
            try:
                revisions = sr.list_revisions(self.db_manager, self.well_id)
            except Exception as exc:
                logger.warning("Survey revisions could not be listed: %s", type(exc).__name__)
                revisions = []
            for revision in revisions:
                self.source_combo.addItem(f"Survey revision {revision['revision']} ({revision['station_count']} "
                                          f"stations, {revision['azimuth_reference']}, {revision['depth_datum']})",
                                          revision["id"])
        index = self.source_combo.findData(current)
        self.source_combo.setCurrentIndex(index if index >= 0 else 0)
        self.source_combo.blockSignals(False)

    def refresh(self, *_signal_args) -> None:
        self.table.setRowCount(0)
        self.history_list.clear()
        self.legacy_list.clear()
        self.views = []
        self._fill_sources()
        if not self.well_id or self.db_manager is None:
            self.status.setText("Select a well to list its saved views.")
            self._update_buttons()
            return
        try:
            self.views = tv.list_views(self.db_manager, self.well_id, include_archived=self.archived_check.isChecked())
            legacy = tv.legacy_plots(self.db_manager, self.well_id)
        except Exception as exc:
            logger.warning("Saved trajectory views could not be read: %s", type(exc).__name__)
            self.status.setText(f"Saved views could not be read ({type(exc).__name__}); nothing is shown.")
            self._update_buttons()
            return
        self.table.setRowCount(len(self.views))
        for row, view in enumerate(self.views):
            source = ("survey revision" if view["source_kind"] == tv.SOURCE_REVISION else
                      "report scope" if view["source_report_id"] else "working survey")
            values = (view["name"], str(view["revision"]), view["status"], source, str(view["station_count"]),
                      "—" if view["wellbore_id"] is None else f"#{view['wellbore_id']}",
                      f"{view['created_at']:%Y-%m-%d %H:%M}" if view["created_at"] else "—")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row)
                self.table.setItem(row, column, item)
        for plot in legacy:
            state = f"{plot['points']} plan point(s)" if plot["readable"] else "UNREADABLE payload"
            self.legacy_list.addItem(f"#{plot['id']} · report {plot['report_id']} ({plot['report_date']}) · "
                                     f"{plot['title'] or 'untitled'} · {state} · read-only")
        self.status.setText(f"{len(self.views)} saved view(s); {len(legacy)} legacy snapshot(s) (read-only).")
        self._update_buttons()

    def selected(self) -> Optional[dict]:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        row = rows.pop()
        return self.views[row] if 0 <= row < len(self.views) else None

    def select_view(self, view_key: str) -> bool:
        for row, view in enumerate(self.views):
            if view["view_key"] == view_key:
                self.table.selectRow(row)
                return True
        return False

    def _update_buttons(self) -> None:
        view = self.selected()
        has_well = bool(self.well_id and self.db_manager is not None)
        self.save_btn.setEnabled(has_well)
        for button in (self.open_btn, self.clone_btn, self.compare_btn, self.export_csv_btn, self.export_json_btn):
            button.setEnabled(view is not None)
        self.revise_btn.setEnabled(view is not None and view["status"] == tv.ACTIVE)
        self.archive_btn.setEnabled(view is not None and view["status"] == tv.ACTIVE)
        self.restore_btn.setEnabled(view is not None and view["status"] == tv.ARCHIVED)

    def _show_history(self) -> None:
        self.history_list.clear()
        view = self.selected()
        self._update_buttons()
        if view is None:
            return
        try:
            for record in tv.history(self.db_manager, view["view_key"]):
                self.history_list.addItem(
                    f"rev {record['revision']} · {record['action']} · {record['status']} · {record['station_count']} "
                    f"stations · {record['integrity']} · {record['note'] or '—'}")
        except Exception as exc:
            logger.warning("View history could not be read: %s", type(exc).__name__)
            self.history_list.addItem(f"History could not be read ({type(exc).__name__}).")

    # ------------------------------------------------------------------ actions
    def _fail(self, title: str, message: str) -> None:
        self.status.setText(f"NOT SAVED — {message}")
        QMessageBox.warning(self, title, f"NOT SAVED\n\n{message}")

    def _done(self, record: dict, message: str) -> dict:
        self.last_result = record
        self.refresh()
        self.select_view(record["view_key"])
        self.status.setText(message)
        return record

    def _source_kwargs(self, ctx: dict) -> dict:
        revision_id = self.source_combo.currentData()
        if revision_id:
            return {"survey_revision_id": int(revision_id), "report_id": None}
        return {"survey_revision_id": None, "report_id": ctx.get("report_id")}

    def save_current(self) -> Optional[dict]:
        ctx = self._context()
        if not ctx.get("well_id") or self.db_manager is None:
            self._fail("Save view", "Select a well first.")
            return None
        name, ok = QInputDialog.getText(self, "Save trajectory view", "View name:")
        if not ok:
            self.status.setText("Save cancelled — NOT SAVED.")
            return None
        note, _ok = QInputDialog.getText(self, "Save trajectory view", "Note (optional):")
        try:
            record = tv.save_view(self.db_manager, ctx["well_id"], name, ctx["settings"],
                                  wellbore_id=ctx.get("wellbore_id"), note=note or "", **self._source_kwargs(ctx))
        except tv.TrajectoryViewError as exc:
            self._fail("Save view", str(exc))
            return None
        except Exception as exc:
            logger.exception("Saving a trajectory view failed")
            self._fail("Save view", f"The database refused the view ({type(exc).__name__}).")
            return None
        return self._done(record, f"Saved view '{record['name']}' revision {record['revision']} "
                                  f"({record['station_count']} stations).")

    def open_selected(self) -> Optional[tuple]:
        view = self.selected()
        if view is None:
            return None
        record = tv.get_view(self.db_manager, view["id"])
        state = tv.drift(self.db_manager, record)
        self.details.setPlainText(
            f"View '{record['name']}' revision {record['revision']} ({record['status']}) — integrity "
            f"{record['integrity']}\nCurrent data: {state.state} — {state.reason}\n"
            f"Snapshot SHA-256 {record['stations_sha256']}")
        self.status.setText(f"Opened '{record['name']}' revision {record['revision']}: {state.state}.")
        self.last_result = record
        self.view_opened.emit(record["id"])
        return record, state

    def revise_selected(self) -> Optional[dict]:
        view = self.selected()
        if view is None:
            return None
        ctx = self._context()
        if ctx.get("well_id") != view["well_id"]:
            self._fail("Revise view", "The viewer shows another well; select the view's well first.")
            return None
        note, ok = QInputDialog.getText(self, "Revise trajectory view", "What changed (required):")
        if not ok or not (note or "").strip():
            self.status.setText("Revision cancelled or no reason given — NOT SAVED.")
            return None
        try:
            record = tv.revise_view(self.db_manager, view["view_key"], expected_revision=view["revision"],
                                    settings=ctx["settings"], note=note, **self._source_kwargs(ctx))
        except tv.TrajectoryViewError as exc:
            self._fail("Revise view", str(exc))
            return None
        except Exception as exc:
            logger.exception("Revising a trajectory view failed")
            self._fail("Revise view", f"The database refused the revision ({type(exc).__name__}).")
            return None
        return self._done(record, f"Saved revision {record['revision']} of '{record['name']}'.")

    def clone_selected(self) -> Optional[dict]:
        view = self.selected()
        if view is None:
            return None
        name, ok = QInputDialog.getText(self, "Clone trajectory view", "Name of the copy:",
                                        text=f"{view['name']} (copy)")
        if not ok:
            self.status.setText("Clone cancelled — NOT SAVED.")
            return None
        try:
            record = tv.clone_view(self.db_manager, view["id"], name)
        except tv.TrajectoryViewError as exc:
            self._fail("Clone view", str(exc))
            return None
        except Exception as exc:
            logger.exception("Cloning a trajectory view failed")
            self._fail("Clone view", f"The database refused the copy ({type(exc).__name__}).")
            return None
        return self._done(record, f"Saved copy '{record['name']}' of revision {view['revision']} of "
                                  f"'{view['name']}'.")

    def _status_change(self, archive: bool) -> Optional[dict]:
        view = self.selected()
        if view is None:
            return None
        verb = "Archive" if archive else "Restore"
        reason, ok = QInputDialog.getText(self, f"{verb} trajectory view", "Reason (required):")
        if not ok or not (reason or "").strip():
            self.status.setText(f"{verb} cancelled or no reason given — NOT SAVED.")
            return None
        call = tv.archive_view if archive else tv.restore_view
        try:
            record = call(self.db_manager, view["view_key"], expected_revision=view["revision"], reason=reason)
        except tv.TrajectoryViewError as exc:
            self._fail(f"{verb} view", str(exc))
            return None
        except Exception as exc:
            logger.exception("Changing a trajectory view status failed")
            self._fail(f"{verb} view", f"The database refused the change ({type(exc).__name__}).")
            return None
        if archive and not self.archived_check.isChecked():
            self.archived_check.setChecked(True)          # keep the archived view visible after the change
        return self._done(record, f"'{record['name']}' is now {record['status']} (revision {record['revision']}).")

    def archive_selected(self) -> Optional[dict]:
        return self._status_change(True)

    def restore_selected(self) -> Optional[dict]:
        return self._status_change(False)

    def compare_selected(self) -> Optional[dict]:
        view = self.selected()
        if view is None:
            return None
        if view["parent_id"] is None:
            self.details.setPlainText("Revision 1 has no previous revision to compare with.")
            self.last_compare = None
            return None
        older, newer = tv.get_view(self.db_manager, view["parent_id"]), tv.get_view(self.db_manager, view["id"])
        try:
            result = tv.compare(older, newer)
        except tv.TrajectoryViewError as exc:
            self.details.setPlainText(f"Not compared: {exc}")
            self.last_compare = None
            return None
        unit = "m"
        lines = [f"Revision {older['revision']} → {newer['revision']} ({result['method']})",
                 "Identical snapshot." if result["identical"] else "Snapshots differ.",
                 f"Settings changed: {', '.join(result['settings_changed']) or 'none'}",
                 f"Paired stations: {len(result['paired'])}; only in older: {len(result['only_in_older'])}; "
                 f"only in newer: {len(result['only_in_newer'])}"]
        for key, value in result["max_abs_delta"].items():
            suffix = "°" if key in ("inc", "azi") else ("°/30 m" if key == "dls" else f" {unit}")
            lines.append(f"max |Δ{key}| = {'—' if value is None else f'{value:.4f}{suffix}'}")
        self.details.setPlainText("\n".join(lines))
        self.last_compare = result
        return result

    def _export_csv(self) -> None:
        self.export_selected("csv")

    def _export_json(self) -> None:
        self.export_selected("json")

    def export_selected(self, kind: str) -> Optional[int]:
        view = self.selected()
        if view is None:
            return None
        record = tv.get_view(self.db_manager, view["id"])
        unit = (self._context().get("settings") or {}).get("unit") or record["settings"].get("unit", "m")
        pattern = "CSV files (*.csv)" if kind == "csv" else "JSON files (*.json)"
        path, _ = QFileDialog.getSaveFileName(self, "Export saved trajectory view", "", pattern)
        if not path:
            self.status.setText("Export cancelled — nothing written.")
            return None
        try:
            count = (tv.export_csv if kind == "csv" else tv.export_json)(path, record, unit)
        except (tv.TrajectoryViewError, OSError) as exc:
            self.status.setText(f"NOT EXPORTED — {exc}")
            QMessageBox.warning(self, "Export view", f"NOT EXPORTED\n\n{exc}")
            return None
        self.status.setText(f"Exported {count} stored station(s) of '{record['name']}' revision "
                            f"{record['revision']} in {unit} to {path}.")
        return count
