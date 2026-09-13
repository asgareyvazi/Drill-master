"""Read-only Torque & Drag calculation-history browser (mission §11–§16).

This dialog is a *record viewer*, not an input form: it lists persisted T&D
runs, shows the frozen historical details of a selected run, and offers an
observational "Verify" action that recomputes the run from its own snapshot and
reports MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE. It never edits or
deletes history, and verification never overwrites a stored result.

The dialog owns no engineering logic — it delegates entirely to
``TorqueDragCalculationRepository`` and the Qt-free
``torque_drag_persistence`` domain, so all reconstruction/verification remains
testable without Qt.
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

from core.engineering.torque_drag_persistence import (
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


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def build_history_rows(saved_list) -> List[dict]:
    """Qt-free view-model: turn SavedCalculation objects into row dicts.

    Kept separate from widget code so the list projection is unit-testable
    without constructing any Qt object.
    """
    rows = []
    for s in saved_list:
        created = getattr(s, "created_at", None)
        rows.append({
            "id": s.id,
            "when": created.strftime("%Y-%m-%d %H:%M") if created else "—",
            "method": s.method or "—",
            "components": s.component_count,
            "survey": s.survey_count,
            "pickup": s.summary.get("hookload_pickup"),
            "buoyed": s.summary.get("total_buoyed_weight"),
            "torque": s.summary.get("surface_torque_rotating_ft_lbf"),
            "references": len(s.reference_fingerprints),
            "well_id": s.well_id,
        })
    return rows


class TorqueDragHistoryDialog(QDialog):
    """Browse + inspect + verify persisted Torque & Drag runs (read-only)."""

    def __init__(self, repository, current_method: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self._repo = repository
        self._current_method = current_method
        self._saved: List = []
        self.setWindowTitle("Torque & Drag — Calculation History")
        self.resize(920, 560)
        self._build_ui()
        self.reload()

    # ---- UI construction -------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)

        header = QLabel(
            "Persisted Torque & Drag runs. Each row is an immutable historical "
            "record; select one to inspect its frozen inputs and verify it "
            "against the current engine.")
        header.setWordWrap(True)
        header.setStyleSheet("color:#555; padding:2px;")
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Saved", "Method", "Comp", "Survey", "Pickup (klbf)",
             "Buoyed (klbf)", "Refs"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
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

    # ---- data ------------------------------------------------------------
    def reload(self):
        """(Re)load history from the repository, handling empty/failure states."""
        try:
            self._saved = self._repo.all() if self._repo else []
        except Exception as exc:  # DB unavailable / corrupt — fail soft
            self._saved = []
            self.count_label.setText(f"⚠️ Could not load history: {exc}")
            self.table.setRowCount(0)
            return

        rows = build_history_rows(self._saved)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = [
                row["when"], row["method"], str(row["components"]),
                str(row["survey"]), _fmt(row["pickup"], 1),
                _fmt(row["buoyed"], 1), str(row["references"]),
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
        snap = s.input_snapshot or {}
        params = snap.get("parameters", {}) or {}
        lines = [
            "IDENTITY",
            f"  Type            : Torque & Drag ({s.label or 'run'})",
            f"  Saved           : {s.created_at}",
            f"  Well context    : {s.well_id if s.well_id is not None else 'none (standalone)'}",
            f"  Method          : {s.method}",
            f"  Snapshot schema : v{s.snapshot_schema_version}",
            "",
            "INPUT PARAMETERS",
            f"  Mud density     : {_fmt(params.get('mud_density_ppg'), 3, ' ppg')}",
            f"  Friction factor : {_fmt(params.get('friction_factor'), 3)}",
            f"  WOB             : {_fmt(params.get('wob_klbf'), 2, ' klbf')}",
            f"  Wellbore ID     : {_fmt(params.get('wellbore_id_in'), 3, ' in')}",
            f"  Survey stations : {s.survey_count}",
            "",
            f"DRILL STRING ({s.component_count} component(s))",
        ]
        for i, comp in enumerate(snap.get("components", []) or [], 1):
            fp = comp.get("reference_fingerprint")
            trace = f"  [catalog ref: {fp}]" if fp else "  [manual input — no catalog reference]"
            lines.append(
                f"  {i}. {comp.get('type', 'pipe')}: "
                f"OD {_fmt(comp.get('od'), 3)} in / ID {_fmt(comp.get('id'), 3)} in / "
                f"{_fmt(comp.get('weight'), 2)} ppf / {_fmt(comp.get('length'), 1)} m / "
                f"{comp.get('grade', '—')} / {comp.get('connection', '—')}")
            lines.append(trace)
        lines += [
            "",
            "REFERENCE TRACEABILITY",
            f"  Fingerprints    : {', '.join(s.reference_fingerprints) or 'none (all manual)'}",
            "",
            "STORED RESULT (historical claim)",
            f"  Pickup hookload : {_fmt(s.summary.get('hookload_pickup'), 2, ' klbf')}",
            f"  Slackoff hookld : {_fmt(s.summary.get('hookload_slackoff'), 2, ' klbf')}",
            f"  Rotating hookld : {_fmt(s.summary.get('hookload_rotating'), 2, ' klbf')}",
            f"  Surface torque  : {_fmt(s.summary.get('surface_torque_rotating_ft_lbf'), 1, ' ft-lbf')}",
            f"  Buoyed weight   : {_fmt(s.summary.get('total_buoyed_weight'), 2, ' klbf')}",
        ]
        return "\n".join(lines)

    # ---- verification (observational; never mutates history) -------------
    def _on_verify(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self._saved):
            return
        outcome = self._saved[idx].verify(current_method=self._current_method)
        label, color = _STATUS_STYLE.get(outcome.status, (outcome.status, "#555"))
        parts = [f"<b style='color:{color}'>{label}</b>"]
        if outcome.status == VERIFY_DIFFERENT:
            for d in outcome.differences:
                parts.append(
                    f"{d['key']}: stored {_fmt(d['stored'])} vs "
                    f"recalculated {_fmt(d['recalculated'])}")
        if outcome.status in (VERIFY_NOT_REPRODUCIBLE, VERIFY_UNREADABLE) and outcome.detail:
            parts.append(outcome.detail)
        if not outcome.method_matches:
            parts.append(
                "<span style='color:#c0392b'>Note: the engine method changed "
                "since this run was saved — a numeric match would NOT be an "
                "exact-algorithm reproduction.</span>")
        parts.append("<i>Stored historical result was not modified.</i>")
        self.status_label.setText("<br>".join(parts))
