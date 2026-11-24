"""M418 / M421 / M423 / M427 — one W13 dialog for the declared-input calculation services.

UI → service module (``evaluate`` with declared inputs; validation in the service) → ``save_case`` (immutable
calculation case, inputs SHA-256 as provenance) → Calculation History replay (``core.history_replay`` generic
service adapter). The dialog holds no engineering formula: it reads the service's ``FIELDS`` / ``TEXT_FIELDS`` and
optional row table, shows every unit, and passes the typed text through unchanged. An empty cell is NOT ENTERED
(never 0); a text choice starts as "— not declared —" and is never defaulted. Values copied from the W13 page are
shown as such ("from page") so derived and typed values are distinguishable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

NOT_DECLARED = "— not declared —"
SAVABLE = ("COMPUTED", "VALID")


class EngineeringServiceDialog(QDialog):
    """Generic dialog for one service module (see the module docstring)."""

    def __init__(self, service, *, title: str, labels: Mapping[str, str],
                 choices: Optional[Mapping[str, Sequence[str]]] = None,
                 table: Optional[Tuple[str, Sequence[Tuple[str, str]], int]] = None,
                 page_values: Optional[Mapping[str, Any]] = None, db=None, well_id: Optional[int] = None,
                 user_id=None, object_prefix: str = "svc", parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle(title)
        self.resize(760, 700)
        self.db, self.well_id, self.user_id = db, well_id, user_id
        self.result: Optional[Dict[str, Any]] = None
        self.saved_case: Optional[Dict[str, Any]] = None
        self.table_spec = table
        page_values = dict(page_values or {})
        lay = QVBoxLayout(self)
        banner = QLabel(f"{service.LABEL}.\nMethod {service.METHOD_ID} — {service.METHOD_VERSION}. "
                        "Empty = NOT ENTERED; nothing is defaulted.")
        banner.setObjectName(f"{object_prefix}_banner")
        banner.setWordWrap(True)
        lay.addWidget(banner)
        form = QFormLayout()
        self.edits: Dict[str, QLineEdit] = {}
        self.combos: Dict[str, QComboBox] = {}
        for key, unit, required in getattr(service, "FIELDS", ()):
            edit = QLineEdit()
            edit.setObjectName(f"{object_prefix}_{key}")
            value = page_values.get(key)
            if value is not None:
                edit.setText(f"{value:g}" if isinstance(value, (int, float)) else str(value))
                edit.setToolTip("copied from the W13 page; edit to override")
            edit.setPlaceholderText(f"{unit or 'dimensionless'}; {'required' if required else 'optional'}; "
                                    "empty = not entered")
            self.edits[key] = edit
            suffix = " (from page)" if value is not None else ""
            form.addRow(f"{labels.get(key, key)} [{unit or '–'}]{suffix}:", edit)
        for key, options in (choices or {}).items():
            combo = QComboBox()
            combo.setObjectName(f"{object_prefix}_{key}")
            combo.addItem(NOT_DECLARED, None)
            for option in options:
                combo.addItem(option, option)
            preset = page_values.get(key)
            if preset is not None and combo.findData(preset) >= 0:
                combo.setCurrentIndex(combo.findData(preset))
            self.combos[key] = combo
            form.addRow(f"{labels.get(key, key)}:", combo)
        lay.addLayout(form)
        self.table: Optional[QTableWidget] = None
        if table is not None:
            _key, fields, rows = table
            self.table = QTableWidget(rows, len(fields))
            self.table.setObjectName(f"{object_prefix}_table")
            self.table.setHorizontalHeaderLabels([f"{labels.get(k, k)} ({u})" for k, u in fields])
            for row, values in enumerate(page_values.get("rows") or []):
                self.set_row(row, values)
            lay.addWidget(self.table)
        buttons = QHBoxLayout()
        self.run_btn = QPushButton("Evaluate")
        self.run_btn.setObjectName(f"{object_prefix}_run")
        self.run_btn.clicked.connect(self._run_clicked)
        self.save_btn = QPushButton("Save as calculation case")
        self.save_btn.setObjectName(f"{object_prefix}_save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._save_clicked)
        buttons.addWidget(self.run_btn)
        buttons.addWidget(self.save_btn)
        buttons.addStretch()
        lay.addLayout(buttons)
        self.summary = QLabel("Not run.")
        self.summary.setObjectName(f"{object_prefix}_summary")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary, 1)

    # ---- data ------------------------------------------------------------------------------------------------
    def set_value(self, key: str, value: Any) -> None:
        if key in self.combos:
            combo = self.combos[key]
            combo.setCurrentIndex(max(0, combo.findData(value)) if value is not None else 0)
        else:
            self.edits[key].setText("" if value is None else (f"{value:g}" if isinstance(value, (int, float))
                                                              else str(value)))

    def set_row(self, row: int, values: Mapping[str, Any]) -> None:
        _key, fields, _rows = self.table_spec
        for col, (key, _unit) in enumerate(fields):
            value = values.get(key)
            self.table.setItem(row, col, QTableWidgetItem("" if value is None else
                                                          (f"{value:g}" if isinstance(value, (int, float))
                                                           else str(value))))

    def values(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {key: edit.text().strip() or None for key, edit in self.edits.items()}
        out.update({key: combo.currentData() for key, combo in self.combos.items()})
        return out

    def rows(self) -> List[Dict[str, Any]]:
        if self.table is None:
            return []
        _key, fields, _rows = self.table_spec
        rows = []
        for row in range(self.table.rowCount()):
            cells = {}
            for col, (key, _unit) in enumerate(fields):
                item = self.table.item(row, col)
                cells[key] = (item.text().strip() if item is not None else "") or None
            if any(value is not None for value in cells.values()):     # an entirely empty row is not a row
                rows.append(cells)
        return rows

    # ---- actions ---------------------------------------------------------------------------------------------
    def run(self) -> Optional[Dict[str, Any]]:
        self.save_btn.setEnabled(False)
        self.result = None
        try:
            if self.table is not None:
                result = self.service.evaluate(self.values(), self.rows())
            else:
                result = self.service.evaluate(self.values())
        except ValueError as exc:            # every service error is a ValueError subclass with the reason
            self.summary.setText(f"Not run: {exc}")
            return None
        self.result = result
        self.summary.setText("\n".join(self.service.summary_lines(result)))
        self.save_btn.setEnabled(result.get("status") in SAVABLE and self.db is not None)
        return result

    def save(self) -> Optional[Dict[str, Any]]:
        from core.authorization import AuthorizationError

        if self.result is None or self.db is None:
            return None
        try:
            case = self.service.save_case(self.db, self.result, well_id=self.well_id, user_id=self.user_id)
        except (ValueError, AuthorizationError) as exc:
            self.summary.setText(self.summary.text() + f"\nNot saved: {exc}")
            return None
        self.saved_case = case
        self.save_btn.setEnabled(False)
        self.summary.setText(self.summary.text() + f"\nSaved as calculation case #{case['id']} "
                             "(replayable from Calculation History).")
        self.after_save(case)
        return case

    def after_save(self, case: Dict[str, Any]) -> None:
        """Hook for subclasses (the dull-grade dialog refreshes its trend)."""

    def _run_clicked(self, _checked=False):
        self.run()

    def _save_clicked(self, _checked=False):
        self.save()


# ---- the four services ------------------------------------------------------------------------------------------
HB_LABELS = {"hole_id_in": "Hole / casing ID", "pipe_od_in": "Pipe OD", "length_ft": "Section length",
             "flow_rate_gpm": "Flow rate", "density_ppg": "Mud density", "tau0_lbf_100ft2": "HB yield stress τ0",
             "k_lbf_sn_100ft2": "HB consistency K", "n_index": "HB flow index n",
             "roughness_in": "Wall roughness (absolute)", "transition_criterion": "Transition band"}


def hb_slot_dialog(page_values=None, **kwargs) -> EngineeringServiceDialog:
    from core import hydraulics_hb_slot as hb

    return EngineeringServiceDialog(hb, title="Annular loss — Herschel-Bulkley slot (R-HYD-2, SCREENING)",
                                    labels=HB_LABELS, choices={"transition_criterion": hb.CRITERIA},
                                    page_values=page_values, object_prefix="m416", **kwargs)


SS_LABELS = {**HB_LABELS, "trip_speed_ft_min": "Pipe speed (magnitude)", "clinging_constant": "Clinging constant K_c",
             "tvd_ft": "TVD at the bit (optional)", "pipe_end": "String end", "hole_id_in": "Hole / casing ID",
             "pipe_od_in": "String OD in the section", "length_ft": "Section length"}


def surge_swab_dialog(page_values=None, **kwargs) -> EngineeringServiceDialog:
    from core import hydraulics_hb_slot as hb
    from core import surge_swab as ss

    return EngineeringServiceDialog(ss, title="Surge / swab — quasi-steady, closed-end (SCREENING)", labels=SS_LABELS,
                                    choices={"transition_criterion": hb.CRITERIA, "pipe_end": ss.PIPE_ENDS},
                                    table=("sections", ss.SECTION_FIELDS, 6), page_values=page_values,
                                    object_prefix="m420", **kwargs)


DF_LABELS = {"rpm_tolerance_rpm": "RPM tolerance between steps", "slope_ratio": "Founder slope ratio (0-1)",
             "wob_klbf": "WOB", "rpm": "RPM", "rop_ft_hr": "ROP"}


def drilloff_fitted_dialog(page_values=None, **kwargs) -> EngineeringServiceDialog:
    from core import drilloff_fitted as df

    return EngineeringServiceDialog(df, title="Drill-off test — fitted two-segment line (M423, SCREENING)",
                                    labels=DF_LABELS, table=("steps", df.STEP_FIELDS, 10), page_values=page_values,
                                    object_prefix="m423", **kwargs)


DG_LABELS = {"bit_size_in": "Bit size", "depth_in_m": "Depth in", "depth_out_m": "Depth out", "bit_no": "Bit number",
             "bit_type": "Bit type", "inner": "I — inner rows (0-8)", "outer": "O — outer rows (0-8)",
             "dull_char": "D — dull characteristic", "location": "L — location", "bearings": "B — bearings / seals",
             "gauge": "G — gauge (I or 1/16 in out)", "other_char": "O — other characteristic",
             "reason_pulled": "R — reason pulled", "date_out": "Date out (YYYY-MM-DD)"}


class DullGradeDialog(EngineeringServiceDialog):
    """The service dialog plus the well's saved-grade trend (ordering only)."""

    def __init__(self, page_values=None, **kwargs):
        from core import bit_dull_grade as dg

        super().__init__(_dull_grade_service(), title="Bit dull grade — IADC record (M427)", labels=DG_LABELS,
                         choices={"bit_type": dg.BIT_TYPES, "dull_char": sorted(dg.DULL_CODES),
                                  "other_char": sorted(dg.DULL_CODES), "reason_pulled": sorted(dg.REASON_CODES)},
                         page_values=page_values, object_prefix="m427", **kwargs)
        self.trend_table = QTableWidget(0, 6)
        self.trend_table.setObjectName("m427_trend")
        self.trend_table.setHorizontalHeaderLabels(["Case", "Bit", "Type", "Depth out (m)", "Date out", "Grade"])
        self.layout().addWidget(QLabel("Saved grades of this well (by depth out; no interpretation):"))
        self.layout().addWidget(self.trend_table)
        self.refresh_trend()

    def refresh_trend(self) -> List[Dict[str, Any]]:
        from core import bit_dull_grade as dg

        rows = dg.trend(self.db, self.well_id) if self.db is not None and self.well_id is not None else []
        self.trend_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("case_id", "bit_no", "bit_type", "depth_out_m", "date_out", "grade")):
                value = row[key]
                self.trend_table.setItem(r, c, QTableWidgetItem("" if value is None else
                                                                (f"{value:g}" if isinstance(value, float)
                                                                 else str(value))))
        return rows

    def after_save(self, case):
        self.refresh_trend()


def _dull_grade_service():
    """Adapter exposing ``core.bit_dull_grade`` with its typed fields split into line edits and combos."""
    from types import SimpleNamespace

    from core import bit_dull_grade as dg

    fields = tuple((key, unit, False) for key, unit in dg.NUMBER_FIELDS) + tuple(
        (key, "", key in dg.REQUIRED) for key in ("bit_no", "inner", "outer", "location", "bearings", "gauge",
                                                    "date_out"))
    return SimpleNamespace(METHOD_ID=dg.METHOD_ID, METHOD_VERSION=dg.METHOD_VERSION, LABEL=dg.LABEL, FIELDS=fields,
                           evaluate=dg.evaluate, summary_lines=dg.summary_lines, save_case=dg.save_case)


def dull_grade_dialog(page_values=None, **kwargs) -> DullGradeDialog:
    return DullGradeDialog(page_values=page_values, **kwargs)
