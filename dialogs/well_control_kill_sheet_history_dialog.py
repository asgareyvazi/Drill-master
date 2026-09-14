"""Read-only Well Control kill-sheet calculation-history browser.

The kill-sheet counterpart of the Casing / Cement / T&D history dialogs: it
lists persisted kill-sheet runs, shows the frozen historical details of a
selected run (from the PERSISTED record only — never from current widgets), and
offers an observational "Verify" action that recomputes the whole composite from
its own snapshot and reports MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE.
It never edits or deletes history, and verification never overwrites a stored
result.

It owns no engineering logic and no verification/comparison logic — it delegates
to ``WellControlKillSheetRepository`` and the Qt-free persistence/verification
domain (mission §45/§46). It intentionally does not share widget code with the
other history dialogs: each shows different engineering fields, and a premature
shared dialog base would hide those differences (mission §49).
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
    """Qt-free view-model: turn SavedKillSheetCalculation objects into rows."""
    rows = []
    for s in saved_list:
        created = getattr(s, "created_at", None)
        ci = s.canonical_inputs
        rows.append({
            "id": s.id,
            "when": created.strftime("%Y-%m-%d %H:%M") if created else "—",
            "method": ci.get("method") or s.method,
            "kill_mw": s.summary.get("kill_mw_ppg"),
            "maasp": s.summary.get("maasp_psi"),
            "stk_total": s.summary.get("stk_total"),
            "well_id": s.well_id,
        })
    return rows


class WellControlKillSheetHistoryDialog(QDialog):
    """Browse + inspect + verify persisted kill-sheet runs (read-only)."""

    def __init__(self, repository, current_method: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self._repo = repository
        self._current_method = current_method
        self._saved: List = []
        self.setWindowTitle("Well Control Kill Sheet — Calculation History")
        self.resize(980, 580)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        header = QLabel(
            "Persisted Well Control kill-sheet runs. Each row is an immutable "
            "historical record; select one to inspect its frozen inputs and "
            "verify the whole composite against the current engine.")
        header.setWordWrap(True)
        header.setStyleSheet("color:#555; padding:2px;")
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Saved", "Method", "Kill MW (ppg)", "MAASP (psi)", "Strokes"])
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
            "Recompute the whole kill sheet from its own frozen snapshot and "
            "compare with the stored result. Observational — never rewrites "
            "history.")
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
                row["when"], str(row["method"] or "—"),
                _fmt(row["kill_mw"], 2), _fmt(row["maasp"], 0),
                _fmt(row["stk_total"], 0),
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
        ci = s.canonical_inputs
        res = s.result or {}
        pipes = ci.get("pipes", []) or []
        pipe_lines = [
            f"    {p.get('type', ''):<12} OD {_fmt(p.get('od_in'), 3)}  "
            f"ID {_fmt(p.get('id_in'), 3)}  L {_fmt(p.get('length_ft'), 1, ' ft')}"
            for p in pipes
        ] or ["    (none)"]
        lines = [
            "IDENTITY",
            f"  Type            : Well Control Kill Sheet ({s.label or 'run'})",
            f"  Saved           : {s.created_at}",
            f"  Well context    : {s.well_id if s.well_id is not None else 'none (standalone)'}",
            f"  Method          : {s.method}",
            f"  Kill method     : {ci.get('method', '—')}",
            f"  Snapshot schema : v{s.snapshot_schema_version}",
            "",
            "INPUT (frozen, canonical — reconstructs the composite without any external state)",
            f"  TVD / MD        : {_fmt(ci.get('tvd_ft'), 0, ' ft')} / {_fmt(ci.get('md_ft'), 0, ' ft')}",
            f"  Shoe TVD        : {_fmt(ci.get('shoe_tvd_ft'), 0, ' ft')}",
            f"  Hole / Csg ID   : {_fmt(ci.get('hole_size_in'), 3, ' in')} / {_fmt(ci.get('casing_id_in'), 3, ' in')}",
            f"  Mud weight      : {_fmt(ci.get('mw_ppg'), 2, ' ppg')}",
            f"  Frac gradient   : {_fmt(ci.get('frac_gradient_psi_ft'), 4, ' psi/ft')}",
            f"  SIDPP / SICP    : {_fmt(ci.get('sidpp_psi'), 0, ' psi')} / {_fmt(ci.get('sicp_psi'), 0, ' psi')}",
            f"  Pit gain        : {_fmt(ci.get('pit_gain_bbl'), 1, ' bbl')}",
            f"  SCR1 / SCR2     : {_fmt(ci.get('scr1_psi'), 0, ' psi')}@{_fmt(ci.get('scr1_spm'), 0)} / "
            f"{_fmt(ci.get('scr2_psi'), 0, ' psi')}@{_fmt(ci.get('scr2_spm'), 0)}",
            f"  Pump output     : {_fmt(ci.get('pump_output_bbl_stk'), 5, ' bbl/stk')}",
            f"  Well type       : {ci.get('well_type', '—')}",
            "  Drill string    :",
            *pipe_lines,
            "",
            "STORED RESULT (historical claim — whole composite)",
            f"  Kill MW         : {_fmt(res.get('kill_mw_ppg'), 2, ' ppg')} ({_fmt(res.get('kill_mw_pcf'), 1, ' pcf')})",
            f"  ICP / FCP       : {_fmt(res.get('icp_psi'), 0, ' psi')} / {_fmt(res.get('fcp_psi'), 0, ' psi')}",
            f"  MAASP           : {_fmt(res.get('maasp_psi'), 0, ' psi')}",
            f"  String / Ann    : {_fmt(res.get('total_string_vol_bbl'), 2, ' bbl')} / {_fmt(res.get('total_ann_vol_bbl'), 2, ' bbl')}",
            f"  Total well vol  : {_fmt(res.get('total_well_vol_bbl'), 2, ' bbl')}",
            f"  Strokes (total) : {_fmt(res.get('stk_total'), 0)}",
            f"  Kick type/height: {res.get('kick_type', '—')} / {_fmt(res.get('kick_height_ft'), 0, ' ft')}",
            f"  Choke schedule  : {len(res.get('choke_schedule', []) or [])} point(s)",
            "",
            "NOTE: the kill-sheet pipe program may come from presets, the "
            "DrillPipe catalog, or manual entry, but only numeric geometry is "
            "used and it is frozen here — no reference fingerprint is claimed, "
            "and reconstruction needs no live catalog.",
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
