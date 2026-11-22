"""M67: Calculation history and Engineering Report Center.

One list of every stored calculation (engine snapshots, trajectory, W13
cases, directional plan revisions) through ``core.calculation_history``
adapters: filter, inspect, compare two, recalculate-and-verify with the
current method (stored separately, the original is never changed), export
the list, and render HTML/PDF reports. Reads run on the GUI thread through
short read-only sessions inside the core module; no ORM object reaches Qt.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from core import calculation_history as ch
from core import calculation_clone_contract as ccc
from core import calculation_workbench as wb

logger = logging.getLogger(__name__)
COLUMNS = ("Source", "Name", "Method", "Version", "Created", "Scope", "Derived from")
CLONE_TIP = ("Store a new case with the same inputs and stored results (not recalculated, not approved); "
             "the original stays as it was.")
PAGE_SIZE = 200          # M73: rows per page; filters and paging run in the database


class CalculationHistoryTab(QWidget):
    def __init__(self, db_manager=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_context = None            # M102: full selection context
        self.db = db_manager
        self.well_id: Optional[int] = None
        self.entries: List[ch.HistoryEntry] = []
        self.last_outcome: Optional[dict] = None
        self.setLayoutDirection(Qt.LeftToRight)
        layout = QVBoxLayout(self)

        filters = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItem("All sources", None)
        for source in ch.SOURCES:
            self.source_combo.addItem(source, source)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Filter by name or method…")
        self.well_only = QCheckBox("Selected well only")
        self.well_only.setChecked(True)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_clicked)
        self.source_combo.currentIndexChanged.connect(self._refresh_clicked)
        self.text_edit.returnPressed.connect(self._refresh_clicked)
        self.well_only.toggled.connect(self._refresh_clicked)
        self.show_archived = QCheckBox("Show archived")          # M286: archived records are hidden by default
        self.show_archived.setToolTip("Archived records are kept unchanged; they are only left out of this list.")
        self.show_archived.toggled.connect(self._refresh_clicked)
        self.archived_keys: set = set()
        for widget in (QLabel("Source:"), self.source_combo, self.text_edit, self.well_only, self.show_archived,
                       self.refresh_btn):
            filters.addWidget(widget)
        self.page, self.total = 0, 0
        self.prev_btn, self.next_btn = QPushButton("◀ Newer"), QPushButton("Older ▶")
        self.page_label = QLabel("")
        self.prev_btn.clicked.connect(lambda _checked=False: self.go_page(self.page - 1))
        self.next_btn.clicked.connect(lambda _checked=False: self.go_page(self.page + 1))
        for widget in (self.prev_btn, self.page_label, self.next_btn):
            filters.addWidget(widget)
        layout.addLayout(filters)
        self.statuses_label = QLabel("")     # M73: readable / comparable / reproducible, separately
        self.statuses_label.setWordWrap(True)
        layout.addWidget(self.statuses_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.detail = QTextBrowser()
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.compare_btn = QPushButton("Compare selected (2)")
        self.compare_btn.clicked.connect(self._compare_clicked)
        self.recalc_btn = QPushButton("Recalculate && verify")
        self.recalc_btn.setToolTip("Re-run with the current method and compare with the stored result; nothing is changed.")
        self.recalc_btn.clicked.connect(self._recalc_clicked)
        self.save_recalc_btn = QPushButton("Save recalculation")
        self.save_recalc_btn.setToolTip("Store the recalculated result as a new case; the original stays as it was.")
        self.save_recalc_btn.clicked.connect(self._save_recalc_clicked)
        self.report_btn = QPushButton("Export report…")
        self.report_btn.clicked.connect(self._report_clicked)
        self.export_btn = QPushButton("Export list CSV…")
        self.export_btn.clicked.connect(self._export_clicked)
        self.clone_btn = QPushButton("Clone")                 # M286
        self.clone_btn.setToolTip(CLONE_TIP)
        self.clone_btn.clicked.connect(self._clone_clicked)
        self.archive_btn = QPushButton("Archive…")
        self.archive_btn.setToolTip("Hide the record from this list (reason required, audited); nothing is deleted.")
        self.archive_btn.clicked.connect(self._archive_clicked)
        self.restore_btn = QPushButton("Restore…")
        self.restore_btn.setToolTip("Return an archived record to the list (reason required, audited).")
        self.restore_btn.clicked.connect(self._restore_clicked)
        # M305: bulk archive / restore of the selected rows (preview, one reason, per-row status)
        self.bulk_archive_btn = QPushButton("Archive selected…")
        self.bulk_archive_btn.setToolTip("Preview, then archive every selected record with one reason (per-row "
                                         "status; each row is its own audited transaction).")
        self.bulk_archive_btn.clicked.connect(self._bulk_archive_clicked)
        self.bulk_restore_btn = QPushButton("Restore selected…")
        self.bulk_restore_btn.setToolTip("Preview, then restore every selected archived record with one reason.")
        self.bulk_restore_btn.clicked.connect(self._bulk_restore_clicked)
        # M306: a clone next to its source (read-only; a clone is a copy, not a rerun)
        self.clone_compare_btn = QPushButton("Clone vs source…")
        self.clone_compare_btn.setToolTip("Show a cloned case next to the record it was copied from.")
        self.clone_compare_btn.clicked.connect(self._clone_compare_clicked)
        self.last_bulk: Optional[dict] = None
        self.clone_dialog = None
        for button in (self.compare_btn, self.recalc_btn, self.save_recalc_btn, self.clone_btn, self.archive_btn,
                       self.restore_btn, self.bulk_archive_btn, self.bulk_restore_btn, self.clone_compare_btn,
                       self.report_btn, self.export_btn):
            actions.addWidget(button)
        layout.addLayout(actions)
        lineage = QHBoxLayout()
        lineage.addWidget(QLabel("Lineage:"))
        self.lineage_combo = QComboBox()
        self.lineage_combo.setToolTip("Where the selected calculation came from, and the cases derived from it.")
        self.open_linked_btn = QPushButton("Open linked")
        self.open_linked_btn.clicked.connect(self._open_linked_clicked)
        lineage.addWidget(self.lineage_combo, 1)
        lineage.addWidget(self.open_linked_btn)
        layout.addLayout(lineage)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._update_actions()

    # -- data ---------------------------------------------------------------
    def set_well(self, well_id: Optional[int], _well_data=None) -> None:
        """Follow the selection. A tab hidden inside a tab set reloads when it is
        shown (M70.7); a stand-alone widget loads at once."""
        if (well_id or None) != getattr(self, "well_id", None):
            self.page = 0                     # another well starts at its newest page
        self.well_id = well_id or None
        self._stale = True
        if self.isVisible() or self.parentWidget() is None:
            self.refresh()
        else:
            self.entries = []
            self.table.setRowCount(0)
            self.detail.clear()
            self.last_outcome = None
            self._load_lineage(None)
            self._update_actions()

    def on_context_changed(self, snapshot) -> None:
        """M102: keep the full context (the list itself is scoped by ``set_well``)."""
        self.current_context = snapshot

    def clear_selection(self) -> None:
        """The selection was cleared (e.g. the well was deleted): drop everything shown."""
        self.set_well(None)

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_stale", False):
            self.refresh()

    def refresh(self) -> None:
        self._stale = False
        self.entries = []
        if self.db is not None:
            well = self.well_id if self.well_only.isChecked() else None
            if self.well_only.isChecked() and well is None:
                self.status.setText("Select a well, or clear 'Selected well only'.")
            else:
                source = self.source_combo.currentData()
                filters = {"well_id": well, "sources": [source] if source else None, "text": self.text_edit.text(),
                           "include_archived": self.show_archived.isChecked()}
                self.total = ch.count_history(self.db, **filters)          # M73: COUNT and paging in the database
                pages = max(1, -(-self.total // PAGE_SIZE))
                self.page = min(max(0, self.page), pages - 1)
                self.entries = ch.load_history(self.db, limit=PAGE_SIZE, offset=self.page * PAGE_SIZE, **filters)
                self.status.setText(f"{self.total} calculation(s).")
        pages = max(1, -(-self.total // PAGE_SIZE)) if self.entries else 1
        self.page_label.setText(f"Page {self.page + 1} of {pages}")
        self.prev_btn.setEnabled(self.page > 0)
        self.next_btn.setEnabled(self.page + 1 < pages)
        self.statuses_label.clear()
        self.archived_keys = set()
        if self.db is not None and self.entries:
            with self.db.session_scope() as session:
                hidden = wb.archived_ids(session, {e.table for e in self.entries})
            self.archived_keys = {e.key for e in self.entries if e.record_id in hidden.get(e.table, set())}
        self.table.setRowCount(len(self.entries))
        for row, entry in enumerate(self.entries):
            data = entry.to_row()
            if entry.key in self.archived_keys:
                data["name"] = f"{data['name']} [ARCHIVED]"
            for col, key in enumerate(("source", "name", "method", "version", "created_at", "scope", "parent")):
                self.table.setItem(row, col, QTableWidgetItem(str(data[key])))
        self.detail.clear()
        self.last_outcome = None
        self._load_lineage(None)
        self._update_actions()

    def go_page(self, page: int) -> None:
        self.page = page
        self.refresh()

    def selected(self) -> List[ch.HistoryEntry]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [self.entries[r] for r in rows if r < len(self.entries)]

    def select_rows(self, rows: List[int]) -> None:
        self.table.clearSelection()
        mode = self.table.selectionMode()
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        for row in rows:
            self.table.selectRow(row)
        self.table.setSelectionMode(mode)

    def _update_actions(self) -> None:
        chosen = self.selected() if self.table.selectionModel() is not None else []
        self.compare_btn.setEnabled(len(chosen) == 2)
        self.recalc_btn.setEnabled(len(chosen) == 1)
        self.report_btn.setEnabled(len(chosen) in (1, 2))
        self.save_recalc_btn.setEnabled(bool(self.last_outcome and self.last_outcome.get("values")))
        self.export_btn.setEnabled(bool(self.entries))
        one = chosen[0] if len(chosen) == 1 else None
        refusal = ccc.explain(one) if one is not None else None        # M303: the adapter matrix decides
        self.clone_btn.setEnabled(one is not None and refusal is None)
        self.clone_btn.setToolTip(f"Clone refused: {refusal}" if refusal else CLONE_TIP)
        self.bulk_archive_btn.setEnabled(any(e.key not in self.archived_keys for e in chosen))
        self.bulk_restore_btn.setEnabled(any(e.key in self.archived_keys for e in chosen))
        self.clone_compare_btn.setEnabled(one is not None and one.table == "calculation_cases")
        self.archive_btn.setEnabled(one is not None and one.key not in self.archived_keys)
        self.restore_btn.setEnabled(one is not None and one.key in self.archived_keys)

    # -- actions ------------------------------------------------------------
    def report_html(self) -> str:
        chosen = self.selected()
        if len(chosen) == 1:
            return ch.render_entry_report(chosen[0], well_label=ch.well_label(self.db, chosen[0].well_id))
        if len(chosen) == 2:
            labels = {ch.well_label(self.db, e.well_id) for e in chosen}
            return ch.render_comparison_report(chosen[0], chosen[1], well_label=" / ".join(sorted(labels)))
        return ""

    def compare(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 2:
            return None
        self.detail.setHtml(self.report_html())
        numeric = ch.numeric_differences(*chosen)
        for part in ("inputs", "results"):      # M73: unit-safe differences, inputs and results separately
            lines = [f"{d['key']}: {d['status']} " + (f"{d['a']} → {d['b']} (Δ {d['delta']:.6g} {d['unit']})".rstrip()
                                                      if d["status"] == "DIFFERENT"
                                                      else f"{d['unit_a'] or 'no unit'} vs {d['unit_b'] or 'no unit'}")
                     for d in numeric[part]]
            self.detail.append(f"Numeric {part} differences: " + ("; ".join(lines) if lines else "none"))
        full = ch.full_field_compare(*chosen)   # M108: every field, with units (also in the report HTML)
        return {**ch.compare_entries(*chosen), "numeric": numeric, "full": full}

    def recalculate(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1:
            return None
        outcome = ch.recalculate_entry(chosen[0], db=self.db)
        self.last_outcome = outcome
        method = ("same method" if outcome["method_matches"] else "METHOD CHANGED"
                  if outcome["method_matches"] is False else "method not compared")
        self.status.setText(f"Recalculation: {outcome['status']} ({method}). {outcome['detail']}".strip())
        self._update_actions()
        return outcome

    def save_recalculation(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1 or not self.last_outcome:
            return None
        case = ch.save_recalculation(self.db, chosen[0], self.last_outcome)
        self.refresh()                     # M286 (D83): before the message, which refresh used to overwrite
        self.status.setText(f"Stored recalculation as case #{case['id']}; the original record is unchanged.")
        return case

    # -- M286: clone / archive / restore ------------------------------------
    def _user_id(self) -> Optional[int]:
        from core.permissions import permissions

        user = permissions.user
        value = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
        return value if isinstance(value, int) else None

    def ask_reason(self, title: str) -> Optional[str]:
        """The reason for an archive / restore (None when cancelled). Tests replace this method."""
        text, ok = QInputDialog.getText(self, title, "Reason (kept in the audit log):")
        return text if ok else None

    def clone_selected(self, name: Optional[str] = None) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1:
            return None
        try:
            case = wb.clone(self.db, chosen[0], name, user_id=self._user_id())
        except (wb.WorkbenchError, ValueError, LookupError) as exc:
            self.status.setText(f"Clone refused: {exc}")
            return None
        self.refresh()                                      # before the message: refresh rewrites the status line
        self.status.setText(f"Cloned {chosen[0].key} as case #{case['id']} (inputs and stored results copied, "
                            "not recalculated); the original is unchanged.")
        return case

    def _set_archived(self, archive: bool) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1:
            return None
        verb = "Archive" if archive else "Restore"
        reason = self.ask_reason(f"{verb} {chosen[0].name}")
        if reason is None:
            return None
        try:
            mark = (wb.archive if archive else wb.restore)(self.db, chosen[0], reason, user_id=self._user_id())
        except wb.WorkbenchError as exc:
            self.status.setText(f"{verb} refused: {exc}")
            return None
        self.refresh()
        self.status.setText(f"{verb}d {chosen[0].key}: {mark['reason']}. Nothing was deleted or changed.")
        return mark

    def archive_selected(self) -> Optional[dict]:
        return self._set_archived(True)

    def restore_selected(self) -> Optional[dict]:
        return self._set_archived(False)

    # -- M305: bulk archive / restore ----------------------------------------
    def confirm_bulk(self, preview: dict) -> Optional[str]:
        """Show the per-row preview and ask for the reason (None when cancelled). Tests replace this method."""
        from PySide6.QtWidgets import QMessageBox

        lines = [f"{r['plan']}: {r['key']} {('– ' + r['reason']) if r['reason'] else ''}" for r in preview["rows"]]
        verb = "Archive" if preview["action"] == wb.ARCHIVE else "Restore"
        answer = QMessageBox.question(self, f"{verb} {len(lines)} record(s)",
                                      "\n".join(lines[:40]) + ("\n…" if len(lines) > 40 else "")
                                      + "\n\nEach row is its own audited transaction; nothing is deleted.")
        if answer != QMessageBox.Yes:
            return None
        return self.ask_reason(f"{verb} {preview['counts'][wb.WILL]} record(s)")

    def bulk_set_archived(self, archive: bool) -> Optional[dict]:
        chosen = self.selected()
        if not chosen:
            return None
        action = wb.ARCHIVE if archive else wb.RESTORE
        preview = wb.bulk_preview(self.db, chosen, action)
        if not preview["authorized"]:
            self.status.setText(f"Bulk {action.lower()} refused: {preview['rows'][0]['reason']}")
            return None
        if not preview["counts"][wb.WILL]:
            self.status.setText(f"Nothing to {action.lower()}: " + "; ".join(
                f"{r['key']} {r['reason']}" for r in preview["rows"]))
            return None
        reason = self.confirm_bulk(preview)
        if reason is None:
            return None
        try:
            result = wb.bulk_apply(self.db, chosen, action, reason, user_id=self._user_id())
        except wb.WorkbenchError as exc:
            self.status.setText(str(exc))
            return None
        self.last_bulk = result
        self.refresh()                                       # before the message: refresh rewrites the status line
        details = "; ".join(f"{r['key']} {r['status']}" + (f" ({r['detail']})" if r["status"] != wb.DONE else "")
                            for r in result["rows"])
        self.status.setText(f"{result['message']} {details}")
        return result

    def _bulk_archive_clicked(self, _checked=False):
        self.bulk_set_archived(True)

    def _bulk_restore_clicked(self, _checked=False):
        self.bulk_set_archived(False)

    # -- M306: clone vs source -----------------------------------------------
    def clone_comparison(self) -> Optional[dict]:
        chosen = self.selected()
        if len(chosen) != 1 or chosen[0].table != "calculation_cases":
            return None
        from dialogs.clone_comparison_dialog import CloneComparisonDialog

        comparison = ccc.side_by_side(self.db, chosen[0].record_id)
        if comparison["status"] == "NOT_A_CLONE":
            self.status.setText(f"{chosen[0].key} is not a clone; there is no source to compare with.")
            return comparison
        self.clone_dialog = CloneComparisonDialog(comparison, self)
        self.clone_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self.clone_dialog.open()
        self.status.setText(f"Clone vs source: {comparison['status']} (copy, not a rerun).")
        return comparison

    def _clone_compare_clicked(self, _checked=False):
        self.clone_comparison()

    def _clone_clicked(self, _checked=False):
        self.clone_selected()

    def _archive_clicked(self, _checked=False):
        self.archive_selected()

    def _restore_clicked(self, _checked=False):
        self.restore_selected()

    def export_report(self, path: str) -> bool:
        html = self.report_html()
        if not html:
            return False
        try:
            if path.lower().endswith(".pdf"):
                document = QTextDocument()
                document.setHtml(html)
                writer = QPdfWriter(path)
                writer.setPageSize(QPageSize(QPageSize.A4))
                document.print_(writer)
            else:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(html)
        except OSError as exc:
            logger.error("Report export failed: %s", exc)
            self.status.setText(f"Report export failed: {exc}")
            return False
        self.status.setText(f"Report written to {path}.")
        return True

    def _selection_changed(self):
        chosen = self.selected()
        self.last_outcome = None
        self.statuses_label.clear()
        if len(chosen) == 1:
            self.detail.setHtml(self.report_html())
            state = ch.entry_status(chosen[0])
            self.statuses_label.setText(f"Readable: {state['readable']} · Comparable: {state['comparable']} · "
                                        f"Reproducible: {state['reproducible']} ({state['reproducible_reason']})")
        self._load_lineage(chosen[0] if len(chosen) == 1 else None)
        self._update_actions()

    # -- lineage (M70.5) ------------------------------------------------------
    def _load_lineage(self, entry: Optional[ch.HistoryEntry]) -> None:
        self.lineage_combo.clear()
        if entry is None or self.db is None:
            self.open_linked_btn.setEnabled(False)
            return
        for link in ch.lineage(self.db, entry):
            self.lineage_combo.addItem(link["label"], link["key"])
        if not self.lineage_combo.count():
            self.lineage_combo.addItem("No linked calculations", None)
        self.open_linked_btn.setEnabled(self.lineage_combo.currentData() is not None)

    def open_linked(self, key: Optional[str] = None) -> bool:
        """Select the linked record; filters that hide it are cleared first."""
        key = key or self.lineage_combo.currentData()
        if not key:
            return False
        rows = [i for i, e in enumerate(self.entries) if e.key == key]
        if not rows and self.db is not None:
            for widget in (self.source_combo, self.text_edit):     # no refresh per cleared filter
                widget.blockSignals(True)
            self.source_combo.setCurrentIndex(0)
            self.text_edit.clear()
            for widget in (self.source_combo, self.text_edit):
                widget.blockSignals(False)
            well = self.well_id if self.well_only.isChecked() else None
            page = ch.page_of(self.db, key, page_size=PAGE_SIZE, well_id=well)    # M88: the record's own page
            if page is not None:
                self.page = page
            self.refresh()
            rows = [i for i, e in enumerate(self.entries) if e.key == key]
        if not rows:
            self.status.setText(f"{key} is not available (deleted, or outside the selected well).")
            return False
        self.select_rows(rows[:1])
        self.table.scrollToItem(self.table.item(rows[0], 0))
        return True

    def _open_linked_clicked(self, _checked=False):
        self.open_linked()

    def _refresh_clicked(self, *_):
        self.page = 0
        self.refresh()

    def _compare_clicked(self, _checked=False):
        self.compare()

    def _recalc_clicked(self, _checked=False):
        self.recalculate()

    def _save_recalc_clicked(self, _checked=False):
        self.save_recalculation()

    def _report_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export report", "calculation_report.html",
                                              "HTML (*.html);;PDF (*.pdf)")
        if path:
            self.export_report(path)

    def _export_clicked(self, _checked=False):
        path, _ = QFileDialog.getSaveFileName(self, "Export history", "calculation_history.csv", "CSV (*.csv)")
        if path:
            count = ch.export_history_csv(self.entries, path)
            self.status.setText(f"Exported {count} row(s) to {path}.")
