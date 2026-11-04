"""Read-only MSE (Teale) calculation-history browser.

The MSE counterpart of the Cement / Casing / T&D history dialogs: it lists
persisted MSE runs, shows the frozen historical details of a selected run, and
offers an observational "Verify" action that recomputes the run from its own
snapshot and reports MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE. It never
edits or deletes history, and verification never overwrites a stored result.

It owns no engineering logic — it delegates to ``MSECalculationRepository`` and
the Qt-free persistence/verification domain. It intentionally does not share
widget code with the other history dialogs: each shows different engineering
fields, and a premature shared dialog base would hide those differences (mission
§44 — extraction only if it improves correctness/maintenance, not for symmetry).
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from core.repositories import mse_repository as mr

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


def lineage_text(s) -> str:
    """M123 (D6): the run's lineage class; a legacy run shows the one legacy label.  Works on detached
    ``SavedMSECalculation`` objects and on plain fakes without lineage attributes (treated as legacy)."""
    cls = getattr(s, "lineage_class", None)
    if cls is None:
        cls = mr.lineage_class(getattr(s, "well_id", None), getattr(s, "lineage_version", None),
                               getattr(s, "wellbore_id", None), getattr(s, "md_m", None))
    return mr.LEGACY_LABEL if cls == mr.CLASS_LEGACY else cls


def repairable_fields(s) -> List[str]:
    """Lineage fields of ``s`` that are unknown and not already repaired (none without a well)."""
    if getattr(s, "well_id", None) is None or not hasattr(s, "repair_for"):
        return []
    return [name for name in mr.REPAIRABLE_FIELDS if getattr(s, name, None) is None and s.repair_for(name) is None]


def build_history_rows(saved_list) -> List[dict]:
    """Qt-free view-model: turn SavedMSECalculation objects into row dicts."""
    rows = []
    for s in saved_list:
        created = getattr(s, "created_at", None)
        params = s.input_parameters
        rows.append({
            "id": s.id,
            "when": created.strftime("%Y-%m-%d %H:%M") if created else "—",
            "wob": params.get("wob_lbf"),
            "rpm": params.get("rpm"),
            "rop": params.get("rop_ft_hr"),
            "bit": params.get("bit_diameter_in"),
            "mse": s.summary.get("mse_psi"),
            "well_id": s.well_id,
            "lineage": lineage_text(s),
        })
    return rows


class MSEHistoryDialog(QDialog):
    """Browse + inspect + verify persisted MSE runs (read-only)."""

    def __init__(self, repository, current_method: Optional[str] = None,
                 parent=None, well_id: Optional[int] = None,
                 well_label: Optional[str] = None):
        super().__init__(parent)
        self._repo = repository
        self._current_method = current_method
        self._well_id = well_id
        self._well_label = well_label
        self._saved: List = []
        self.setWindowTitle("MSE (Teale) — Calculation History")
        self.resize(960, 560)
        self._build_ui()
        self.reload()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        header = QLabel(
            "Persisted MSE (Mechanical Specific Energy) runs. Each row is an "
            "immutable historical record; select one to inspect its frozen "
            "inputs and verify it against the current engine.")
        header.setWordWrap(True)
        header.setStyleSheet("color:#555; padding:2px;")
        outer.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Saved", "Bit (in)", "ROP (ft/hr)", "MSE (psi)", "Lineage"])
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

        self.repair_btn = QPushButton("🧾 Repair lineage…")
        self.repair_btn.setToolTip(
            "Record an audited repair of ONE unknown lineage field (wellbore, report or measured depth) from "
            "evidence you name. Never inferred; the run record itself is not changed.")
        self.repair_btn.setEnabled(False)
        self.repair_btn.clicked.connect(self._on_repair)
        rlay.addWidget(self.repair_btn)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        from dialogs.history_well_filter import make_scope_checkbox
        self.scope_box = make_scope_checkbox(self._well_label)
        self.scope_box.toggled.connect(self.reload)
        self.scope_box.setVisible(self._well_id is not None)
        bottom.addWidget(self.scope_box)
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
            from dialogs.history_well_filter import filter_saved_by_well
            all_saved = self._repo.all() if self._repo else []
            self._saved = filter_saved_by_well(
                all_saved, self._well_id,
                self.scope_box.isChecked() if hasattr(self, 'scope_box') else False)
        except Exception as exc:
            self._saved = []
            self.count_label.setText(f"⚠️ Could not load history: {exc}")
            self.table.setRowCount(0)
            return

        rows = build_history_rows(self._saved)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = [
                row["when"], _fmt(row["bit"], 3),
                _fmt(row["rop"], 1), _fmt(row["mse"], 0), row["lineage"],
            ]
            for j, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if j == 0:
                    item.setData(Qt.UserRole, i)
                self.table.setItem(i, j, item)
        self.details.clear()
        self.status_label.clear()
        self.verify_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)
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
            self.repair_btn.setEnabled(False)
            return
        self.verify_btn.setEnabled(True)
        self.repair_btn.setEnabled(bool(repairable_fields(self._saved[idx]))
                                   and hasattr(self._repo, "repair_lineage"))
        self.status_label.clear()
        self.details.setPlainText(self._describe(self._saved[idx]))

    def _describe(self, s) -> str:
        p = s.input_parameters
        lines = [
            "IDENTITY",
            f"  Type            : MSE / Teale ({s.label or 'run'})",
            f"  Saved           : {s.created_at}",
            f"  Well context    : {s.well_id if s.well_id is not None else 'none (standalone)'}",
            f"  Method          : {s.method}",
            f"  Snapshot schema : v{s.snapshot_schema_version}",
            "",
            "INPUT (frozen — reconstructs the calculation without any external state)",
            f"  WOB             : {_fmt(p.get('wob_lbf'), 0, ' lbf')}",
            f"  RPM             : {_fmt(p.get('rpm'), 0, ' rpm')}",
            f"  Torque          : {_fmt(p.get('torque_ft_lbf'), 0, ' ft·lbf')}",
            f"  ROP             : {_fmt(p.get('rop_ft_hr'), 1, ' ft/hr')}",
            f"  Bit diameter    : {_fmt(p.get('bit_diameter_in'), 3, ' in')}",
            "",
            "STORED RESULT (historical claim)",
            f"  MSE             : {_fmt(s.summary.get('mse_psi'), 0, ' psi')}",
            f"  Axial term      : {_fmt(s.summary.get('axial_term_psi'), 0, ' psi')}",
            f"  Rotary term     : {_fmt(s.summary.get('rotary_term_psi'), 0, ' psi')}",
            f"  Bit area        : {_fmt(s.summary.get('bit_area_in2'), 4, ' in²')}",
            "",
            "NOTE: MSE inputs are direct drilling parameters (no catalog/preset), "
            "so no reference fingerprint is claimed — the frozen numeric snapshot "
            "alone reproduces this run.",
            "",
        ]
        lines.extend(self._lineage_lines(s))
        return "\n".join(lines)

    def _lineage_lines(self, s) -> List[str]:
        """M123 (D6): what is known about where and at what depth this run was made, and how it is known."""
        if getattr(s, "lineage_version", None) is None and not getattr(s, "repairs", ()):
            return ["LINEAGE", f"  {mr.LEGACY_LABEL}",
                    "  Saved before lineage was recorded: wellbore, report and depth are unknown and are never",
                    "  taken from the current selection. An audited repair can add one from named evidence."]

        def shown(value, unit=""):
            return "not recorded" if value is None else f"{value}{unit}"
        md = getattr(s, "md_m", None)
        md_text = ("not recorded" if md is None else
                   f"{md:.2f} m (entered {getattr(s, 'md_entered_value', None):g} {getattr(s, 'md_entered_unit', '')})")
        lines = ["LINEAGE (recorded at save)",
                 f"  Class           : {lineage_text(s)}",
                 f"  Lineage version : {shown(getattr(s, 'lineage_version', None))}",
                 f"  Wellbore        : {shown(getattr(s, 'wellbore_id', None) and f'#{s.wellbore_id}')}",
                 f"  Daily report    : {shown(getattr(s, 'report_id', None) and f'#{s.report_id}')}",
                 f"  Measured depth  : {md_text}",
                 f"  Input source    : {shown(getattr(s, 'input_source', None))}"]
        units = getattr(s, "input_units", None)
        if units:
            lines.append("  Input units     : " + ", ".join(f"{k} {v}" for k, v in units.items()))
        for r in getattr(s, "repairs", ()):
            lines += ["", f"AUDITED REPAIR #{r.id} — {r.field}",
                      f"  Before          : {r.before_value}",
                      f"  After           : {r.value_label}" + ("  (reference since deleted: unknown again)"
                                                               if r.unlinked else ""),
                      f"  Evidence        : {r.evidence}",
                      f"  Reason          : {r.reason}",
                      f"  Confirmed by    : {r.confirmer} at {r.confirmed_at} UTC ({r.method_version})"]
        return lines

    def _on_repair(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self._saved):
            return
        dlg = RepairLineageDialog(self._repo, self._saved[idx], parent=self)
        if dlg.exec():
            self.reload()

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


class RepairLineageDialog(QDialog):
    """M123 (D6): record ONE audited lineage repair - field, value from the run's own well, evidence, reason.

    The confirming user is the identified user of this session; the repository refuses the repair without
    one, without evidence or reason, for a recorded field, for a field already repaired or for a value of
    another well.  Errors are shown in the dialog (``error_label``); nothing is inferred or pre-filled.
    """

    FIELD_TEXT = {"wellbore_id": "Wellbore", "report_id": "Daily report", "md_m": "Measured depth (MD)"}

    def __init__(self, repository, saved, parent=None):
        super().__init__(parent)
        self._repo, self._saved = repository, saved
        self.repair_id: Optional[int] = None
        self.setWindowTitle(f"Repair lineage — MSE run #{saved.id}")
        choices = repository.repair_choices(saved.id)
        form = QFormLayout(self)
        intro = QLabel(f"Current lineage: {lineage_text(saved)}. A repair adds ONE unknown field from evidence "
                       "you name; the run record is not changed and the repair cannot be edited later.")
        intro.setWordWrap(True)
        form.addRow(intro)
        self.field_combo = QComboBox()
        for name in repairable_fields(saved):
            self.field_combo.addItem(self.FIELD_TEXT[name], name)
        form.addRow("Field:", self.field_combo)
        self.wellbore_combo = QComboBox()
        self.wellbore_combo.addItem("— choose —", None)
        for bore_id, name in choices["wellbores"]:
            self.wellbore_combo.addItem(f"{name} (#{bore_id})", bore_id)
        form.addRow("Wellbore:", self.wellbore_combo)
        self.report_combo = QComboBox()
        self.report_combo.addItem("— choose —", None)
        for report_id, label, _bore in choices["reports"]:
            self.report_combo.addItem(label, report_id)
        form.addRow("Daily report:", self.report_combo)
        md_row = QHBoxLayout()
        self.md_spin = QDoubleSpinBox()
        self.md_spin.setRange(0.0, 20000.0)
        self.md_spin.setDecimals(2)
        self.md_unit = QComboBox()
        self.md_unit.addItems(list(mr.MD_UNITS))
        md_row.addWidget(self.md_spin)
        md_row.addWidget(self.md_unit)
        form.addRow("Measured depth:", md_row)
        self.evidence_edit = QPlainTextEdit()
        self.evidence_edit.setPlaceholderText("Required: the document, report page or log this value is taken from.")
        self.evidence_edit.setFixedHeight(70)
        form.addRow("Evidence:", self.evidence_edit)
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Required: why the repair is made.")
        form.addRow("Reason:", self.reason_edit)
        confirmer = repository.confirmer_label()
        self.confirmer_label = QLabel(confirmer or "No identified user — a repair cannot be confirmed.")
        form.addRow("Confirmed by:", self.confirmer_label)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#c0392b")
        form.addRow(self.error_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Record audited repair")
        self.buttons.accepted.connect(self.submit)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self.field_combo.currentIndexChanged.connect(self._sync)
        self._sync()

    def _sync(self, *_args):
        name = self.field_combo.currentData()
        self.wellbore_combo.setEnabled(name == "wellbore_id")
        self.report_combo.setEnabled(name == "report_id")
        self.md_spin.setEnabled(name == "md_m")
        self.md_unit.setEnabled(name == "md_m")

    def submit(self) -> bool:
        name = self.field_combo.currentData()
        kwargs = {}
        if name == "wellbore_id":
            kwargs["wellbore_id"] = self.wellbore_combo.currentData()
            if kwargs["wellbore_id"] is None:
                self.error_label.setText("Choose the wellbore.")
                return False
        elif name == "report_id":
            kwargs["report_id"] = self.report_combo.currentData()
            if kwargs["report_id"] is None:
                self.error_label.setText("Choose the daily report.")
                return False
        elif name == "md_m":
            kwargs.update(md_value=self.md_spin.value(), md_unit=self.md_unit.currentText())
        else:
            self.error_label.setText("Nothing can be repaired on this run.")
            return False
        try:
            self.repair_id = self._repo.repair_lineage(self._saved.id, name, evidence=self.evidence_edit.toPlainText(),
                                                       reason=self.reason_edit.text(), **kwargs)
        except (ValueError, PermissionError) as exc:      # refused: shown, nothing written
            self.error_label.setText(str(exc))
            return False
        self.accept()
        return True
