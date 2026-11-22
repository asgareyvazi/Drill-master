"""W3b "Architecture" page (M74): validated, immutable architecture revisions.

The W3b casing / formation / completion editors stay the editor; this page
validates what is drawn, freezes it as a numbered revision tied to the
wellbore and a survey revision, reloads a stored revision into the schematic
(generated from the records) and derives cement annulus intervals for the
worksheet. GUI thread only; database work is short and synchronous.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core import cement_job_reconciliation as cj
from core import well_architecture as wa
from core.authorization import AuthorizationError

logger = logging.getLogger(__name__)


class WellArchitecturePanel(QWidget):
    COLUMNS = ("Rev", "Components", "Warnings", "Survey rev", "Wellbore", "Created")

    def __init__(self, owner, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.owner = owner
        self.revisions: List[Dict[str, Any]] = []
        layout = QVBoxLayout(self)
        note = QLabel("Validates the schematic being drawn and freezes it as an immutable revision. "
                      "Unknown sizes stay unknown; cement volumes are a WORKSHEET (nominal sizes).")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.survey_combo = QComboBox()
        self.validate_btn = QPushButton("Validate drawing")
        self.freeze_btn = QPushButton("Freeze as revision")
        self.load_btn = QPushButton("Load into schematic")
        self.validate_btn.clicked.connect(lambda _c=False: self.validate_current())
        self.freeze_btn.clicked.connect(lambda _c=False: self.freeze_current())
        self.load_btn.clicked.connect(lambda _c=False: self.load_selected())
        self.compare_btn = QPushButton("Compare with previous")        # M311: component-level revision diff
        self.compare_btn.setObjectName("architecture_compare_btn")
        self.compare_btn.clicked.connect(self._compare_clicked)
        for widget in (QLabel("Survey revision:"), self.survey_combo, self.validate_btn, self.freeze_btn,
                       self.load_btn, self.compare_btn):
            row.addWidget(widget)
        layout.addLayout(row)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 1)
        cement = QHBoxLayout()
        self.string_combo = QComboBox()
        self.hole_spin = QDoubleSpinBox()
        self.hole_spin.setRange(0.0, 60.0)
        self.hole_spin.setDecimals(3)
        self.hole_spin.setSpecialValueText("recorded")      # 0 = use the recorded hole size, never assume one
        self.hole_spin.setSuffix(" in")
        self.caliper_spin = QDoubleSpinBox()          # M89: declared average open-hole caliper
        self.caliper_spin.setRange(0.0, 60.0)
        self.caliper_spin.setDecimals(3)
        self.caliper_spin.setSpecialValueText("none")
        self.caliper_spin.setSuffix(" in")
        self.caliper_spin.setToolTip("Average open-hole caliper from a log; 'none' = not declared.")
        self.excess_spin = QDoubleSpinBox()           # M89: explicit excess on open hole only
        self.excess_spin.setRange(-1.0, wa.MAX_EXCESS_PCT)
        self.excess_spin.setDecimals(1)
        self.excess_spin.setValue(-1.0)
        self.excess_spin.setSpecialValueText("none")
        self.excess_spin.setSuffix(" %")
        self.excess_spin.setToolTip("Excess applied to open-hole intervals only; 'none' = no excess (0 % is a "
                                    "declared zero).")
        self.cement_btn = QPushButton("Cement annulus")
        self.cement_btn.clicked.connect(lambda _c=False: self.cement_selected())
        self.save_cement_btn = QPushButton("Save worksheet")
        self.save_cement_btn.clicked.connect(lambda _c=False: self.save_cement_case())
        self.last_cement: Optional[Dict[str, Any]] = None
        for widget in (QLabel("String:"), self.string_combo, QLabel("Open hole:"), self.hole_spin,
                       QLabel("Caliper:"), self.caliper_spin, QLabel("Excess:"), self.excess_spin, self.cement_btn,
                       self.save_cement_btn):
            cement.addWidget(widget)
        layout.addLayout(cement)
        # M317: a recorded cement job (W3c cement report) against the selected revision and string.
        job_row = QHBoxLayout()
        self.job_combo = QComboBox()
        self.job_combo.setObjectName("cement_job_combo")
        self.yield_unit_combo = QComboBox()
        self.yield_unit_combo.setObjectName("cement_yield_unit")
        self.yield_unit_combo.addItem("not declared", None)       # the report does not store the yield unit
        for unit in cj.YIELD_UNITS:
            self.yield_unit_combo.addItem(unit, unit)
        self.reconcile_btn = QPushButton("Reconcile recorded job")
        self.reconcile_btn.setObjectName("cement_reconcile_btn")
        self.reconcile_btn.clicked.connect(self._reconcile_clicked)
        self.save_reconcile_btn = QPushButton("Save reconciliation")
        self.save_reconcile_btn.setObjectName("cement_reconcile_save_btn")
        self.save_reconcile_btn.clicked.connect(self._save_reconcile_clicked)
        self.last_reconciliation: Optional[Dict[str, Any]] = None
        self.last_comparison: Optional[Dict[str, Any]] = None
        for widget in (QLabel("Recorded cement job:"), self.job_combo, QLabel("Yield unit:"), self.yield_unit_combo,
                       self.reconcile_btn, self.save_reconcile_btn):
            job_row.addWidget(widget)
        layout.addLayout(job_row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        # M329: the revision comparison as a table, exportable with its revision SHAs (hidden until compared).
        from core import architecture_diff as ad

        self.diff_table = QTableWidget(0, len(ad.TABLE_COLUMNS))
        self.diff_table.setObjectName("architecture_diff_table")
        self.diff_table.setHorizontalHeaderLabels(list(ad.TABLE_COLUMNS))
        self.diff_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.diff_table.setVisible(False)
        layout.addWidget(self.diff_table, 1)
        diff_row = QHBoxLayout()
        self.diff_unchanged_check = QCheckBox("Show unchanged components")
        self.diff_unchanged_check.setObjectName("architecture_diff_unchanged")
        self.diff_unchanged_check.toggled.connect(lambda _c=False: self._fill_diff_table())
        self.export_diff_btn = QPushButton("Export comparison…")
        self.export_diff_btn.setObjectName("architecture_diff_export_btn")
        self.export_diff_btn.clicked.connect(lambda _c=False: self.export_comparison())
        diff_row.addWidget(self.diff_unchanged_check)
        diff_row.addStretch(1)
        diff_row.addWidget(self.export_diff_btn)
        self.diff_controls = QWidget()
        self.diff_controls.setLayout(diff_row)
        self.diff_controls.setVisible(False)
        layout.addWidget(self.diff_controls)
        self._update_actions()

    # -- context ------------------------------------------------------------
    @property
    def db(self):
        return getattr(self.owner, "db", None)

    @property
    def well_id(self) -> Optional[int]:
        return getattr(self.owner, "current_well_id", None)

    def refresh(self) -> None:
        from core import survey_revisions as sr

        self.revisions, surveys = [], []
        self.last_comparison = None            # M329: a comparison never outlives the well/revision list it came from
        self._fill_diff_table()
        if self.db is not None and self.well_id:
            try:
                self.revisions = wa.list_revisions(self.db, self.well_id)
                surveys = sr.list_revisions(self.db, self.well_id)
            except Exception as exc:  # shown and logged; the schematic keeps working
                logger.warning("architecture revisions could not be read: %s", exc)
                self.status.setText(f"Architecture revisions could not be read: {exc}")
        self.job_combo.clear()
        if self.db is not None and self.well_id:
            try:
                for job in cj.list_jobs(self.db, self.well_id):
                    self.job_combo.addItem(f"#{job['id']} {job['name'] or job['job_type'] or 'cement job'}", job["id"])
            except Exception as exc:  # shown and logged; the schematic keeps working
                logger.warning("cement reports could not be read: %s", exc)
        self.survey_combo.clear()
        self.survey_combo.addItem("(none)", None)
        for survey in surveys:
            self.survey_combo.addItem(f"rev {survey['revision']} ({survey['station_count']} stations)", survey["id"])
        self.table.setRowCount(len(self.revisions))
        for index, rev in enumerate(self.revisions):
            values = (rev["revision"], rev["component_count"], len(rev["validation"]["warnings"]),
                      rev["survey_revision_id"] or "", rev["wellbore_id"] or "", rev["created_at"] or "")
            for col, value in enumerate(values):
                self.table.setItem(index, col, QTableWidgetItem(str(value)))
        self._update_actions()

    def _selected(self) -> Optional[Dict[str, Any]]:
        rows = self.table.selectionModel().selectedRows()
        return self.revisions[rows[0].row()] if rows and rows[0].row() < len(self.revisions) else None

    def _selection_changed(self) -> None:
        self.last_cement = None
        self.last_reconciliation = None
        rev = self._selected()
        self.string_combo.clear()
        if rev is not None:
            for item in rev["components"]:
                if item["kind"] in wa.STRINGS and any(c["kind"] == "cement" and c["name"] == item["name"]
                                                      for c in rev["components"]):
                    self.string_combo.addItem(item["name"])
            warnings = rev["validation"]["warnings"]
            self.status.setText(f"Revision {rev['revision']}: {rev['component_count']} components; "
                                + ("warnings: " + "; ".join(warnings) if warnings else "no warnings"))
        self._update_actions()

    def _update_actions(self) -> None:
        has_well = self.db is not None and bool(self.well_id)
        selected = self._selected() is not None
        self.validate_btn.setEnabled(has_well)
        self.freeze_btn.setEnabled(has_well)
        self.load_btn.setEnabled(selected)
        if hasattr(self, "compare_btn"):
            rev = self._selected()
            self.compare_btn.setEnabled(rev is not None and any(r["revision"] < rev["revision"]
                                                                 for r in self.revisions))
        self.cement_btn.setEnabled(selected and self.string_combo.count() > 0)
        self.save_cement_btn.setEnabled(getattr(self, "last_cement", None) is not None)
        if hasattr(self, "reconcile_btn"):
            self.reconcile_btn.setEnabled(selected and self.string_combo.count() > 0 and self.job_combo.count() > 0)
            self.save_reconcile_btn.setEnabled(self.last_reconciliation is not None
                                               and self.last_reconciliation["status"] == "COMPUTED")

    # -- actions --------------------------------------------------------------
    def current_components(self) -> List[Dict[str, Any]]:
        return wa.from_schematic(self.owner.schematic)

    def validate_current(self) -> Dict[str, List[str]]:
        result = wa.validate(self.current_components())
        errors, warnings = result["errors"], result["warnings"]
        self.status.setText(("Errors: " + "; ".join(errors) if errors else "No errors.")
                            + (" Warnings: " + "; ".join(warnings) if warnings else ""))
        return result

    def freeze_current(self) -> Optional[Dict[str, Any]]:
        from core.selection_manager import SelectionManager

        if self.db is None or not self.well_id:
            return None
        parent = self.revisions[0]["id"] if self.revisions else None
        try:
            rev = wa.save_revision(self.db, self.well_id, self.current_components(),
                                   wellbore_id=SelectionManager().wellbore_for(self.well_id, db=self.db),
                                   survey_revision_id=self.survey_combo.currentData(), parent_id=parent)
        except (wa.ArchitectureError, AuthorizationError) as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.refresh()
        self.status.setText(f"Saved architecture revision {rev['revision']} ({rev['component_count']} components).")
        return rev

    def load_selected(self) -> bool:
        rev = self._selected()
        if rev is None:
            return False
        try:
            stored = wa.get_revision(self.db, rev["id"])
        except (wa.ArchitectureError, LookupError) as exc:
            self.status.setText(f"Not loaded: {exc}")
            return False
        self.owner.schematic = wa.to_schematic(stored["components"], well_name=self.owner.schematic.well_name)
        self.owner._sync_tables_to_schematic()
        self.owner.refresh_drawing()
        self.status.setText(f"Schematic generated from architecture revision {stored['revision']}.")
        return True

    def cement_selected(self) -> Optional[Dict[str, Any]]:
        rev = self._selected()
        if rev is None or not self.string_combo.currentText():
            return None
        hole = self.hole_spin.value() or None
        caliper = self.caliper_spin.value() or None
        excess = self.excess_spin.value() if self.excess_spin.value() >= 0 else None
        try:
            result = wa.cement_annulus(rev["components"], self.string_combo.currentText(), open_hole_in=hole,
                                       caliper_in=caliper, excess_pct=excess)
        except (wa.ArchitectureError, ValueError) as exc:
            self.status.setText(f"Cement annulus not derived: {exc}")
            return None
        parts = [f"{i['top_md']:g}-{i['bottom_md']:g} m in {i['outer']} ({i['outer_source']}): "
                 + (f"{i['volume_bbl']:.2f} bbl" if i["volume_bbl"] is not None else "size unknown")
                 + (f" incl. {i['excess_bbl']:.2f} bbl excess" if i["excess_bbl"] else "")
                 for i in result["intervals"]]
        total = f"{result['total_bbl']:.2f} bbl" if result["total_bbl"] is not None else "not computable"
        self.status.setText(f"{wa.CEMENT_WORKSHEET_LABEL}. {result['label']} - architecture rev {rev['revision']}: "
                            + "; ".join(parts)
                            + f". Total {total}.")
        self.last_cement = {**result, "architecture_revision_id": rev["id"],
                            "architecture_revision": rev["revision"], "components_sha256": rev["components_sha256"],
                            "open_hole_in": hole, "wellbore_id": rev.get("wellbore_id")}
        self._update_actions()
        return self.last_cement

    def compare_selected(self) -> Optional[Dict[str, Any]]:
        """M311: the selected revision against the next older one (read-only; pinned worksheets are listed)."""
        from core import architecture_diff as ad

        rev = self._selected()
        older = max((r for r in self.revisions if rev is not None and r["revision"] < rev["revision"]),
                    key=lambda r: r["revision"], default=None)
        if rev is None or older is None:
            self.status.setText("Select a revision that has an older revision to compare with.")
            return None
        try:
            result = ad.compare_revisions(self.db, older["id"], rev["id"])
        except (ad.ArchitectureDiffError, wa.ArchitectureError, LookupError) as exc:
            self.status.setText(f"Not compared: {exc}")
            return None
        self.last_comparison = result
        self.status.setText(" ".join(ad.summary_lines(result, limit=12)))
        self._fill_diff_table()
        return result

    def _fill_diff_table(self) -> None:
        from core import architecture_diff as ad

        result = self.last_comparison
        rows = ad.table_rows(result, include_unchanged=self.diff_unchanged_check.isChecked()) if result else []
        self.diff_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                text = ad._show(value) if j in (5, 6) else str(value)
                self.diff_table.setItem(i, j, QTableWidgetItem(text))
        self.diff_table.setVisible(result is not None)
        self.diff_controls.setVisible(result is not None)

    def export_comparison(self, path: Optional[str] = None) -> Optional[str]:
        """M329: write the last comparison as CSV or XLSX (metadata with both revision SHA-256s, then the table)."""
        from core import architecture_diff as ad

        result = self.last_comparison
        if result is None:
            self.status.setText("Compare two revisions before exporting.")
            return None
        if path is None:
            from PySide6.QtWidgets import QFileDialog

            name = f"architecture_rev{result['older']['revision']}_vs_rev{result['newer']['revision']}.xlsx"
            path, _filter = QFileDialog.getSaveFileName(self, "Export comparison", name,
                                                        "Excel (*.xlsx);;CSV (*.csv)")
            if not path:
                return None
        try:
            written = ad.export(result, path, include_unchanged=self.diff_unchanged_check.isChecked())
        except (ad.ArchitectureDiffError, OSError) as exc:
            self.status.setText(f"Comparison not exported: {exc}")
            return None
        self.status.setText(f"Comparison exported to {written}.")
        return written

    def _compare_clicked(self, _checked: bool = False):
        self.compare_selected()

    def reconcile_selected(self) -> Optional[Dict[str, Any]]:
        """M317: the selected recorded cement job against the selected revision and string (WORKSHEET)."""
        rev, job_id = self._selected(), self.job_combo.currentData()
        self.last_reconciliation = None
        if rev is None or job_id is None or not self.string_combo.currentText():
            self.status.setText("Select an architecture revision, a cemented string and a recorded cement job.")
            self._update_actions()
            return None
        try:
            result = cj.reconcile(self.db, job_id, rev["id"], self.string_combo.currentText(),
                                  yield_unit=self.yield_unit_combo.currentData(),
                                  open_hole_in=self.hole_spin.value() or None,
                                  caliper_in=self.caliper_spin.value() or None)
        except (cj.ReconciliationError, LookupError, wa.ArchitectureError) as exc:
            self.status.setText(f"Not reconciled: {exc}")
            self._update_actions()
            return None
        self.last_reconciliation = result
        self.status.setText(" ".join(cj.summary_lines(result)))
        self._update_actions()
        return result

    def _reconcile_clicked(self, _checked: bool = False):
        self.reconcile_selected()

    def save_reconciliation(self) -> Optional[Dict[str, Any]]:
        if self.last_reconciliation is None:
            return None
        try:
            case = cj.save_case(self.db, self.last_reconciliation)
        except (ValueError, AuthorizationError) as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.status.setText(f"Reconciliation saved as calculation case #{case['id']}. {cj.LABEL}.")
        self.last_reconciliation = None
        self._update_actions()
        return case

    def _save_reconcile_clicked(self, _checked: bool = False):
        self.save_reconciliation()

    def save_cement_case(self) -> Optional[Dict[str, Any]]:
        """Store the worksheet as an immutable calculation case pinned to the architecture revision."""
        from core import calculation_cases as cc

        work = self.last_cement
        if work is None or self.db is None or not self.well_id:
            return None
        inputs, results = wa.cement_case_payload(work)      # M109: one builder for save and re-run
        try:
            case = cc.save_case(self.db, calculator=wa.CEMENT_CALCULATOR,
                                name=f"Cement annulus {work['string']} (arch rev {work['architecture_revision']})",
                                inputs=inputs, results=results, method=work["method"],
                                method_version=work["version"], well_id=self.well_id,
                                wellbore_id=work.get("wellbore_id"),
                                note=f"{wa.CEMENT_WORKSHEET_LABEL} — {work['label']}")
        except (ValueError, AuthorizationError) as exc:
            self.status.setText(f"Not saved: {exc}")
            return None
        self.status.setText(f"Worksheet saved as calculation case #{case['id']} "
                            f"(architecture revision {work['architecture_revision']}). {wa.CEMENT_WORKSHEET_LABEL}.")
        return case
