"""M63: save / reopen / compare / re-run named calculation cases for W13 calculators.

The open calculator page (innermost current tab) is captured generically:
inputs are its editable spin boxes, combo boxes, line edits and check/radio
buttons; results are its result labels (bordered labels), read-only line
edits and read-only text panes. Widgets are keyed by type and creation order
on that page, with the form label kept for display. Cases are immutable
(``core.calculation_cases``): a re-run is stored as a new child case.
"""

from __future__ import annotations

import weakref
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
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


def capture_page(page: QWidget) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    inputs = {key: {"label": _form_label(w), "value": _read(w)} for key, w in _keyed(_inputs(page))}
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
        row.addWidget(QLabel("Cases:"))
        for widget in (self.save_btn, self.case_combo, self.reopen_btn, self.compare_btn, self.rerun_btn):
            row.addWidget(widget)
        layout.addLayout(row)
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
        for widget in (self.reopen_btn, self.compare_btn, self.rerun_btn):
            widget.setEnabled(enabled and self.case_combo.count() > 0)
        self.save_btn.setEnabled(enabled)

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

        well_id = self._well_id()
        case = cc.save_case(self.db, calculator=self.calculator(), name=name, inputs=inputs, results=results,
                            well_id=well_id, wellbore_id=SelectionManager().wellbore_for(well_id, db=self.db))
        self.refresh()
        self.status.setText(f"Saved case '{case['name']}' (#{case['id']}) with {len(inputs)} inputs and "
                            f"{len(results)} results; {case['method_version']}.")
        return case

    def reopen(self, case_id: int) -> List[str]:
        case = cc.get_case(self.db, case_id)
        if case["calculator"] != self.calculator() and self.finder is not None:
            self.finder.open_path(case["calculator"])
        missing = restore_page(innermost_page(self.tabs), case["inputs"])
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
        child = cc.record_rerun(self.db, case, results)
        self.refresh()
        self.status.setText(f"Re-run stored as case #{child['id']} (parent #{case['id']}); the original is unchanged.")
        return child

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
