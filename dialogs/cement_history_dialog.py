"""Read-only Cement job-volume calculation-history browser.

The cement counterpart of the Casing / T&D history dialogs: it lists persisted
cement job-volume runs, shows the frozen historical details of a selected run,
and offers an observational "Verify" action that recomputes the run from its own
snapshot and reports MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE. It never
edits or deletes history, and verification never overwrites a stored result.

It owns no engineering logic — it delegates to ``CementCalculationRepository``
and the Qt-free persistence/verification domain. It intentionally does not share
widget code with the other history dialogs: the three show different engineering
fields, and a premature shared dialog base would hide those differences (mission
§35 — extraction only if it improves correctness/maintenance, not for symmetry).
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
    """Qt-free view-model: turn SavedCementCalculation objects into row dicts."""
    rows = []
    for s in saved_list:
        created = getattr(s, "created_at", None)
        params = s.input_parameters
        rows.append({
            "id": s.id,
            "when": created.strftime("%Y-%m-%d %H:%M") if created else "—",
            "hole": params.get("hole_size_in"),
            "csg_od": params.get("casing_od_in"),
            "length": params.get("open_hole_length_ft"),
            "slurry": s.summary.get("slurry_volume_bbl"),
            "total_pump": s.summary.get("total_pump_bbl"),
            "sacks": s.summary.get("sacks"),
            "well_id": s.well_id,
        })
    return rows


class CementHistoryDialog(QDialog):
    """Browse + inspect + verify persisted cement job-volume runs (read-only)."""

    def __init__(self, repository, current_method: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self._repo = repository
        self._current_method = current_method
        self._saved: List = []
        self.setWindowTitle("Cement Job Volume — Calculation History")
        self.resize(960, 560)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        header = QLabel(
            "Persisted cement job-volume runs. Each row is an immutable "
            "historical record; select one to inspect its frozen inputs and "
            "verify it against the current engine.")
        header.setWordWrap(True)
        header.setStyleSheet("color:#555; padding:2px;")
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Saved", "Hole (in)", "Csg OD (in)", "Slurry (bbl)", "Sacks"])
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
                row["when"], _fmt(row["hole"], 3), _fmt(row["csg_od"], 3),
                _fmt(row["slurry"], 2),
                _fmt(row["sacks"], 0) if row["sacks"] is not None else "n/a",
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
            f"  Type            : Cement Job Volume ({s.label or 'run'})",
            f"  Saved           : {s.created_at}",
            f"  Well context    : {s.well_id if s.well_id is not None else 'none (standalone)'}",
            f"  Method          : {s.method}",
            f"  Snapshot schema : v{s.snapshot_schema_version}",
            "",
            "INPUT (frozen — reconstructs the calculation without any external state)",
            f"  Hole size       : {_fmt(p.get('hole_size_in'), 3, ' in')}",
            f"  Casing OD / ID  : {_fmt(p.get('casing_od_in'), 3, ' in')} / {_fmt(p.get('casing_id_in'), 3, ' in')}",
            f"  Cement length   : {_fmt(p.get('open_hole_length_ft'), 0, ' ft')}",
            f"  Excess          : {_fmt(p.get('excess_pct'), 0, ' %')}",
            f"  Shoe track      : {_fmt(p.get('shoe_track_ft'), 0, ' ft')}",
            f"  Slurry density  : {_fmt(p.get('slurry_density_ppg'), 2, ' ppg')}",
            f"  Slurry yield    : {_fmt(p.get('yield_ft3_sk'), 3, ' ft³/sk')}",
            f"  Spacer len/MW   : {_fmt(p.get('spacer_length_ft'), 0, ' ft')} / {_fmt(p.get('spacer_density_ppg'), 2, ' ppg')}",
            f"  Lead len/MW     : {_fmt(p.get('lead_length_ft'), 0, ' ft')} / {_fmt(p.get('lead_density_ppg'), 2, ' ppg')}",
            f"  Tail len/MW     : {_fmt(p.get('tail_length_ft'), 0, ' ft')} / {_fmt(p.get('tail_density_ppg'), 2, ' ppg')}",
            f"  Column TVD      : {_fmt(p.get('tvd_column_ft'), 0, ' ft')}",
            f"  Pump rate       : {_fmt(p.get('pump_rate_bbl_min'), 2, ' bbl/min')}",
            "",
            "STORED RESULT (historical claim)",
            f"  Annulus+excess  : {_fmt(s.summary.get('annular_with_excess_bbl'), 2, ' bbl')}",
            f"  Slurry volume   : {_fmt(s.summary.get('slurry_volume_bbl'), 2, ' bbl')}",
            f"  Displacement    : {_fmt(s.summary.get('displacement_volume_bbl'), 2, ' bbl')}",
            f"  Total pump      : {_fmt(s.summary.get('total_pump_bbl'), 2, ' bbl')}",
            f"  Sacks           : {_fmt(s.summary.get('sacks'), 0)}",
            f"  Hydrostatic     : {_fmt(s.summary.get('hydrostatic_psi'), 0, ' psi')}",
            "",
            "NOTE: cement job-volume inputs are direct engineering values (no "
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
