"""Read-only Mud Volume balance calculation-history browser.

The mud-volume counterpart of the MSE / Cement / Casing / T&D history dialogs: it
lists persisted mud volume balance runs, shows the frozen historical details of a
selected run, and offers an observational "Verify" action that recomputes the run
from its own snapshot and reports MATCH / DIFFERENT / NOT_REPRODUCIBLE /
UNREADABLE. It never edits or deletes history, and verification never overwrites
a stored result.

It owns no engineering logic — it delegates to ``MudVolumeCalculationRepository``
and the Qt-free persistence/verification domain. It intentionally does not share
widget code with the other history dialogs: each shows different engineering
fields, and a premature shared dialog base would hide those differences (mission
§40 — extraction only if it improves correctness/maintenance, not for symmetry).
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.engineering.calculation_verification import (
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
)

_STATUS_STYLE = {
    VERIFY_MATCH: ("✅ MATCH", "#27ae60"),
    VERIFY_DIFFERENT: ("⚠️ DIFFERENT", "#e67e22"),
    VERIFY_NOT_REPRODUCIBLE: ("🚫 NOT REPRODUCIBLE", "#c0392b"),
    VERIFY_UNREADABLE: ("❌ UNREADABLE", "#c0392b"),
}


def _fmt(value, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def build_history_rows(saved_list) -> List[dict]:
    """Qt-free view-model: turn SavedMudVolumeCalculation objects into row dicts."""
    rows = []
    for s in saved_list:
        created = getattr(s, "created_at", None)
        params = s.input_parameters
        rows.append({
            "id": s.id,
            "when": created.strftime("%Y-%m-%d %H:%M") if created else "—",
            "active": params.get("active_volume_bbl"),
            "final": s.summary.get("final_volume_bbl"),
            "net": s.summary.get("net_change_bbl"),
            "well_id": s.well_id,
        })
    return rows


class MudVolumeHistoryDialog(QDialog):
    """Browse + inspect + verify persisted mud volume balance runs (read-only)."""

    def __init__(self, repository, current_method: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self._repo = repository
        self._current_method = current_method
        self._saved: List = []
        self.setWindowTitle("Mud Volume Balance — Calculation History")
        self.resize(960, 560)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        header = QLabel(
            "Persisted mud volume balance runs. Each row is an immutable "
            "historical record; select one to inspect its frozen inputs and "
            "verify it against the current engine.")
        header.setWordWrap(True)
        header.setStyleSheet("color:#555; padding:2px;")
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Saved", "Active (bbl)", "Final (bbl)", "Net (bbl)"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self.table)

        right = QWidget()
        rlay = QVBoxLayout(right)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a calculation to inspect.")
        rlay.addWidget(self.details, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.RichText)
        rlay.addWidget(self.status_label)

        self.verify_btn = QPushButton("🔍 Verify (recalculate from snapshot)")
        self.verify_btn.setToolTip(
            "Recompute this run from its own frozen snapshot and compare with "
            "the stored result. Observational — never rewrites history.")
        self.verify_btn.setEnabled(False)
        self.verify_btn.clicked.connect(self._on_verify)
        rlay.addWidget(self.verify_btn)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        refresh = QPushButton("↻ Refresh")
        refresh.clicked.connect(self.reload)
        bottom.addWidget(refresh)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

    def reload(self):
        try:
            self._saved = self._repo.all() if self._repo else []
        except Exception as exc:
            self._saved = []
            self.count_label.setText(f"⚠️ Could not load history: {exc}")
            self.table.setRowCount(0)
            return

        rows = build_history_rows(self._saved)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = [
                row["when"], _fmt(row["active"], 1),
                _fmt(row["final"], 1), _fmt(row["net"], 1),
            ]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if j == 0:
                    item.setData(Qt.UserRole, i)
                self.table.setItem(i, j, item)
        self.details.clear()
        self.status_label.clear()
        self.verify_btn.setEnabled(False)
        self.count_label.setText(
            "No saved calculations yet." if not rows
            else f"{len(rows)} saved calculation(s).")

    def _selected_index(self) -> Optional[int]:
        items = self.table.selectedItems()
        if not items:
            return None
        return self.table.item(items[0].row(), 0).data(Qt.UserRole)

    def _on_selection(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self._saved):
            self.verify_btn.setEnabled(False)
            return
        self.verify_btn.setEnabled(True)
        self.status_label.clear()
        self.details.setPlainText(self._describe(self._saved[idx]))

    def _describe(self, s) -> str:
        p = s.input_parameters
        lines = [
            "IDENTITY",
            f"  Type            : Mud Volume Balance ({s.label or 'run'})",
            f"  Saved           : {s.created_at}",
            f"  Well context    : {s.well_id if s.well_id is not None else 'none (standalone)'}",
            f"  Method          : {s.method}",
            f"  Snapshot schema : v{s.snapshot_schema_version}",
            "",
            "INPUT (frozen — reconstructs the calculation without any external state)",
            f"  Active volume   : {_fmt(p.get('active_volume_bbl'), 1, ' bbl')}",
            f"  Additions       : {_fmt(p.get('additions_bbl'), 1, ' bbl')}",
            f"  Losses          : {_fmt(p.get('losses_bbl'), 1, ' bbl')}",
            f"  Transfers in    : {_fmt(p.get('transfers_in_bbl'), 1, ' bbl')}",
            f"  Transfers out   : {_fmt(p.get('transfers_out_bbl'), 1, ' bbl')}",
            f"  Returns         : {_fmt(p.get('returns_bbl'), 1, ' bbl')}",
            f"  Dilution        : {_fmt(p.get('dilution_bbl'), 1, ' bbl')}",
            f"  Dumped          : {_fmt(p.get('dumped_bbl'), 1, ' bbl')}",
            "",
            "STORED RESULT (historical claim)",
            f"  Final volume    : {_fmt(s.summary.get('final_volume_bbl'), 1, ' bbl')}",
            f"  Net change      : {_fmt(s.summary.get('net_change_bbl'), 1, ' bbl')}",
            "",
            "NOTE: mud volume balance inputs are direct engineering values (no "
            "catalog/preset), so no reference fingerprint is claimed — the "
            "frozen numeric snapshot alone reproduces this run.",
        ]
        return "\n".join(lines)

    def _on_verify(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self._saved):
            return
        outcome = self._saved[idx].verify(current_method=self._current_method)
        label, color = _STATUS_STYLE.get(outcome.status, (outcome.status, "#555"))
        parts = [f"<b style='color:{color}'>{label}</b>"]
        if outcome.status == VERIFY_DIFFERENT:
            for d in outcome.all_differences[:12]:
                parts.append(
                    f"{d['path']}: stored {_fmt(d['stored'])} vs "
                    f"recalculated {_fmt(d['recalculated'])}")
            if len(outcome.all_differences) > 12:
                parts.append(f"… and {len(outcome.all_differences) - 12} more field(s)")
        if outcome.status in (VERIFY_NOT_REPRODUCIBLE, VERIFY_UNREADABLE) and outcome.detail:
            parts.append(outcome.detail)
        if not outcome.method_matches:
            parts.append(
                "<span style='color:#c0392b'>Note: the engine method changed "
                "since this run was saved — a numeric match would NOT be an "
                "exact-algorithm reproduction.</span>")
        parts.append("<i>Stored historical result was not modified.</i>")
        self.status_label.setText("<br>".join(parts))
