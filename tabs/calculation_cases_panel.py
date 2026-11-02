"""M63: save / reopen / compare / re-run named calculation cases for W13 calculators.

The open calculator page (innermost current tab) is captured generically:
inputs are its editable spin boxes, combo boxes, line edits and check/radio
buttons; results are its result labels (bordered labels), read-only line
edits and read-only text panes. Widgets are keyed by type and creation order
on that page, with the form label kept for display. Cases are immutable
(``core.calculation_cases``): a re-run is stored as a new child case.

M87: contract widgets carry the object name ``w13:<attribute>`` (recorded as
``object``) so a contract binds fields without relying on repeated labels; a
contract's non-widget state (e.g. the nozzle program) is stored as ``extra:``
entries; contract calculators also store the adapter's full-precision results.
Every calculator shows its contract status. Cases can be cloned and exported.
"""

from __future__ import annotations

import weakref
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel,
    QLineEdit, QPushButton, QRadioButton, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core import calculation_cases as cc
from tabs.calculator_finder import _direct_tab_widgets

INPUT_TYPES = (QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit, QCheckBox, QRadioButton)
CALCULATE_WORDS = ("calculate", "compute", "محاسبه")


def innermost_page(tabs: QTabWidget) -> Optional[QWidget]:
    page = tabs.currentWidget()
    while page is not None:
        inner = _direct_tab_widgets(page)
        if not inner or inner[0].currentWidget() is None:
            break
        page = inner[0].currentWidget()
    return page


def _form_label(widget: QWidget) -> str:
    parent = widget.parentWidget()
    layout = parent.layout() if parent is not None else None
    if isinstance(layout, QFormLayout):
        label = layout.labelForField(widget)
        if isinstance(label, QLabel):
            return label.text().strip().rstrip(":")
    return ""


def _inputs(page: QWidget) -> List[QWidget]:
    out = []
    for widget in page.findChildren(QWidget):
        if not isinstance(widget, INPUT_TYPES):
            continue
        if isinstance(widget, QLineEdit) and (
            widget.isReadOnly() or isinstance(widget.parentWidget(), (QAbstractSpinBox, QComboBox))
        ):
            continue
        out.append(widget)
    return out


def _results(page: QWidget) -> List[QWidget]:
    out = []
    for widget in page.findChildren(QWidget):
        if isinstance(widget, QLabel) and "border" in widget.styleSheet():
            out.append(widget)
        elif isinstance(widget, QLineEdit) and widget.isReadOnly() and not isinstance(
                widget.parentWidget(), (QAbstractSpinBox, QComboBox)):
            out.append(widget)
        elif isinstance(widget, QTextEdit) and widget.isReadOnly():
            out.append(widget)
    return out


def _keyed(widgets: List[QWidget]) -> List[Tuple[str, QWidget]]:
    counts: Dict[str, int] = {}
    out = []
    for widget in widgets:
        name = type(widget).__name__
        counts[name] = counts.get(name, 0) + 1
        out.append((f"{name}:{counts[name]}", widget))
    return out


def _read(widget: QWidget) -> Any:
    if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, (QCheckBox, QRadioButton)):
        return widget.isChecked()
    if isinstance(widget, QTextEdit):
        return widget.toPlainText()[:4000]
    return widget.text()


def _entry(widget: QWidget) -> Dict[str, Any]:
    entry = {"label": _form_label(widget), "value": _read(widget)}
    name = widget.objectName()
    if name.startswith("w13:"):
        entry["object"] = name
    return entry


def stamp_contract_widgets(tab: QWidget) -> int:
    """Give every contract input widget of the W13 tab its stable object name ``w13:<attr>``."""
    from core import calculator_contracts as contracts

    count = 0
    for contract in contracts.CONTRACTS.values():
        for spec in contract.inputs:
            widget = getattr(tab, spec.attr, None) if spec.attr else None
            if isinstance(widget, QWidget):
                widget.setObjectName(contracts.OBJECT_PREFIX + spec.attr)
                count += 1
    return count


def capture_page(page: QWidget) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    inputs = {key: _entry(w) for key, w in _keyed(_inputs(page))}
    results = {}
    for key, widget in _keyed(_results(page)):
        value = _read(widget)
        if value not in ("", "--"):
            results[key] = {"label": _form_label(widget), "value": value}
    return inputs, results


def restore_page(page: QWidget, inputs: Dict[str, Any]) -> List[str]:
    """Write stored inputs back; returns the keys that could not be restored."""
    missing = []
    widgets = dict(_keyed(_inputs(page)))
    for key, entry in inputs.items():
        if key.startswith("extra:"):
            continue                # non-widget state: restored by the case bar from the contract
        widget, value = widgets.get(key), cc._value(entry)
        try:
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                widget.setValue(type(widget.value())(value))
            elif isinstance(widget, QComboBox):
                index = widget.findText(str(value))
                if index < 0:
                    raise ValueError(value)
                widget.setCurrentIndex(index)
            elif isinstance(widget, (QCheckBox, QRadioButton)):
                widget.setChecked(bool(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            else:
                raise KeyError(key)
        except (KeyError, TypeError, ValueError):  # silent-ok: reported to the user as not restored
            missing.append(key)
    return missing


class CaseBar(QWidget):
    """Case controls shown under the W13 calculator finder."""

    def __init__(self, tabs: QTabWidget, finder, db=None, owner=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tabs, self.finder, self.db = tabs, finder, db
        self._owner = weakref.ref(owner) if owner is not None else None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.save_btn = QPushButton("Save case…")
        self.save_btn.setToolTip("Store this calculator's inputs and results as a named, immutable case.")
        self.save_btn.clicked.connect(self._save_clicked)
        self.case_combo = QComboBox()
        self.case_combo.setMinimumWidth(240)
        self.case_combo.setToolTip("Saved cases of the open calculator (newest first).")
        self.reopen_btn = QPushButton("Reopen")
        self.reopen_btn.clicked.connect(self._reopen_clicked)
        self.compare_btn = QPushButton("Compare with current")
        self.compare_btn.clicked.connect(self._compare_clicked)
        self.rerun_btn = QPushButton("Re-run & save")
        self.rerun_btn.setToolTip("Restore the case, press the calculator's Calculate button and store a new child case.")
        self.rerun_btn.clicked.connect(self._rerun_clicked)
        self.clone_btn = QPushButton("Clone…")
        self.clone_btn.setToolTip("Store a copy of the selected case under a new name (nothing is recalculated).")
        self.clone_btn.clicked.connect(self._clone_clicked)
        self.export_btn = QPushButton("Export…")
        self.export_btn.setToolTip("Write the selected case (inputs, results, method, units) to a CSV file.")
        self.export_btn.clicked.connect(self._export_clicked)
        row.addWidget(QLabel("Cases:"))
        for widget in (self.save_btn, self.case_combo, self.reopen_btn, self.compare_btn, self.rerun_btn,
                       self.clone_btn, self.export_btn):
            row.addWidget(widget)
        layout.addLayout(row)
        self.contract_label = QLabel("")
        self.contract_label.setWordWrap(True)
        layout.addWidget(self.contract_label)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        tabs.currentChanged.connect(self._page_changed)
        self.refresh()

    # -- context ----------------------------------------------------------
    def _well_id(self) -> Optional[int]:
        owner = self._owner() if self._owner is not None else None
        return getattr(owner, "current_well_id", None) if owner is not None else None

    def calculator(self) -> Optional[str]:
        return self.finder.current_path() if self.finder is not None else None

    def _page_changed(self, _index=0):
        self.refresh()

    def refresh(self) -> None:
        self.case_combo.clear()
        enabled = self.db is not None and bool(self.calculator())
        if enabled:
            for case in cc.list_cases(self.db, calculator=self.calculator()):
                self.case_combo.addItem(f"{case['name']} (#{case['id']})", case["id"])
        for widget in (self.reopen_btn, self.compare_btn, self.rerun_btn, self.clone_btn, self.export_btn):
            widget.setEnabled(enabled and self.case_combo.count() > 0)
        self.save_btn.setEnabled(enabled)
        from core import calculator_contracts as contracts

        status, text = contracts.calculator_status(self.calculator()) if self.calculator() else ("", "")
        self.contract_label.setText(f"Contract status: {status} — {text}." if status else "")

    # -- actions ----------------------------------------------------------
    def save_case(self, name: str) -> Optional[Dict[str, Any]]:
        page = innermost_page(self.tabs)
        if page is None or self.db is None or not self.calculator():
            return None
        inputs, results = capture_page(page)
        if not results:
            self.status.setText("No results on this calculator yet — calculate first, then save the case.")
            return None
        from core.selection_manager import SelectionManager

        from core import calculator_contracts as contracts

        well_id = self._well_id()
        method, version, note = "", cc.W13_UNVERSIONED, ""
        contract = contracts.contract_for(self.calculator())
        if contract is not None:   # M73: field IDs, units and the method version of a contract calculator
            inputs, results, missing = contracts.annotate(contract, inputs, results)
            owner = self._owner() if self._owner is not None else None
            inputs.update(contracts.extra_entries(contract, owner))
            if missing:            # cannot be re-run without these inputs: stored, but honestly unversioned
                note = f"contract {contract.stable_id} inputs not found on the page: {', '.join(missing)}"
            elif contract.structured:
                try:
                    results.update(contracts.structured_results(contract, contracts.input_values(contract, inputs)))
                    method, version = contract.method_id, contract.method_version
                except ValueError as exc:   # stored as captured; not re-runnable with these inputs
                    note = f"contract {contract.stable_id} method rejected the inputs: {exc}"
            else:
                method, version = contract.method_id, contract.method_version
        case = cc.save_case(self.db, calculator=self.calculator(), name=name, inputs=inputs, results=results,
                            method=method, method_version=version, note=note,
                            well_id=well_id, wellbore_id=SelectionManager().wellbore_for(well_id, db=self.db))
        self.refresh()
        self.status.setText(f"Saved case '{case['name']}' (#{case['id']}) with {len(inputs)} inputs and "
                            f"{len(results)} results; {case['method_version']}." + (f" {note}." if note else ""))
        return case

    def reopen(self, case_id: int) -> List[str]:
        case = cc.get_case(self.db, case_id)
        if case["calculator"] != self.calculator() and self.finder is not None:
            self.finder.open_path(case["calculator"])
        missing = restore_page(innermost_page(self.tabs), case["inputs"])
        missing += self._restore_extras(case)
        stored = "; ".join(f"{(v.get('label') if isinstance(v, dict) else '') or k}: {cc._value(v)}"
                           for k, v in list(case["results"].items())[:6])
        self.status.setText(f"Reopened '{case['name']}' (#{case['id']}). Stored results: {stored}"
                            + (f". Not restored: {', '.join(missing)}" if missing else ""))
        return missing

    def compare_current(self, case_id: int) -> Dict[str, Any]:
        case = cc.get_case(self.db, case_id)
        inputs, results = capture_page(innermost_page(self.tabs))
        current = {"id": 0, "name": "current", "calculator": self.calculator(), "inputs": inputs,
                   "results": results, "method_version": cc.W13_UNVERSIONED}
        report = cc.compare_cases(case, current)
        lines = [f"{report['a']} vs current: {len(report['inputs'])} input(s), {len(report['results'])} result(s) differ"]
        lines += [f"{d['label']}: {d['a']} → {d['b']}" for d in (report["inputs"] + report["results"])[:8]]
        self.status.setText("\n".join(lines))
        return report

    def rerun(self, case_id: int) -> Optional[Dict[str, Any]]:
        case = cc.get_case(self.db, case_id)
        missing = self.reopen(case_id)
        page = innermost_page(self.tabs)
        button = next((b for b in page.findChildren(QPushButton)
                       if any(w in b.text().lower() for w in CALCULATE_WORDS)), None)
        if missing:
            self.status.setText("Re-run needs every input restored; press Calculate yourself, then Save case.")
            return None
        if button is not None:
            button.click()          # pages without a button recalculate on input change
        _inputs_now, results = capture_page(page)
        if not results:
            self.status.setText("The calculator produced no results after the re-run; nothing was stored.")
            return None
        from core import calculator_contracts as contracts

        contract = contracts.contract_for(case["calculator"])
        if contract is not None and case["method"] == contract.method_id and contract.structured:
            try:
                results.update(contracts.structured_results(contract, contracts.input_values(contract, case["inputs"])))
            except ValueError as exc:
                self.status.setText(f"Re-run refused by the method ({exc}); nothing was stored.")
                return None
            child = cc.record_rerun(self.db, case, results, method_version=contract.method_version)
        elif contract is not None and case["method"] == contract.method_id:
            _unused, results, _missing = contracts.annotate(contract, {}, results)
            child = cc.record_rerun(self.db, case, results, method_version=contract.method_version)
        else:
            child = cc.record_rerun(self.db, case, results)
        self.refresh()
        self.status.setText(f"Re-run stored as case #{child['id']} (parent #{case['id']}); the original is unchanged.")
        return child

    def _restore_extras(self, case: Dict[str, Any]) -> List[str]:
        """Write a contract case's non-widget state back to the W13 tab; returns what could not be restored."""
        import copy

        from core import calculator_contracts as contracts

        contract = contracts.contract_for(case["calculator"])
        owner = self._owner() if self._owner is not None else None
        missing = []
        for spec in (contract.extras if contract is not None else ()):
            entry = case["inputs"].get(f"extra:{spec.field_id}")
            if entry is None or owner is None or not hasattr(owner, spec.attr):
                if entry is not None:
                    missing.append(f"extra:{spec.field_id}")
                continue
            setattr(owner, spec.attr, copy.deepcopy(cc._value(entry)))
            refresh = getattr(owner, spec.refresh, None) if spec.refresh else None
            if callable(refresh):
                refresh()
        return missing

    def clone(self, case_id: int, name: str) -> Optional[Dict[str, Any]]:
        try:
            child = cc.clone_case(self.db, cc.get_case(self.db, case_id), name)
        except (ValueError, LookupError) as exc:
            self.status.setText(f"Not cloned: {exc}")
            return None
        self.refresh()
        self.status.setText(f"Cloned case #{case_id} as '{child['name']}' (#{child['id']}); the original is unchanged.")
        return child

    def export(self, case_id: int, path: str) -> Optional[str]:
        try:
            text = cc.export_case_csv(cc.get_case(self.db, case_id))
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as exc:
            self.status.setText(f"Export failed: {exc}")
            return None
        self.status.setText(f"Exported case #{case_id} to {path}.")
        return path

    def _clone_clicked(self, _checked=False):
        if self._selected() is None:
            return
        name, ok = QInputDialog.getText(self, "Clone case", "New case name:")
        if ok and name.strip():
            self.clone(self._selected(), name.strip())

    def _export_clicked(self, _checked=False):
        if self._selected() is None:
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Export case", f"case_{self._selected()}.csv",
                                                    "CSV files (*.csv)")
        if path:
            self.export(self._selected(), path)

    def _selected(self) -> Optional[int]:
        return self.case_combo.currentData()

    def _save_clicked(self, _checked=False):
        name, ok = QInputDialog.getText(self, "Save case", "Case name:")
        if ok and name.strip():
            self.save_case(name.strip())

    def _reopen_clicked(self, _checked=False):
        if self._selected() is not None:
            self.reopen(self._selected())

    def _compare_clicked(self, _checked=False):
        if self._selected() is not None:
            self.compare_current(self._selected())

    def _rerun_clicked(self, _checked=False):
        if self._selected() is not None:
            self.rerun(self._selected())
