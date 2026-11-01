"""M63: immutable named calculation cases and the W13 case bar.

Temporary SQLite database, synthetic inputs; widget tests run offscreen (not
Windows desktop testing). The real W13 Quick Calc page is used for the
end-to-end case; its capacity formula is checked against an independent
hand value (ID 4.276 in: ID^2 / 1029.4 = 0.017762 bbl/ft).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFormLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from core import calculation_cases as cc


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db():
    from synthetic_operations import make_file_database

    manager = make_file_database(Path(tempfile.mkdtemp(prefix="m63-cases-")) / "cases.db")
    yield manager
    manager.engine.dispose()


# ---- core ---------------------------------------------------------------------------------------
def test_cases_are_insert_only_and_reruns_are_children(db):
    first = cc.save_case(db, calculator="Mud › Weight", name="SYN base", inputs={"a": {"label": "MW", "value": 10.0}},
                         results={"r": {"label": "Out", "value": "1.2"}})
    assert first["method_version"] == cc.W13_UNVERSIONED
    child = cc.record_rerun(db, first, {"r": {"label": "Out", "value": "1.3"}}, method_version="engine v2")
    assert child["parent_id"] == first["id"] and "method version changed" in child["note"]
    assert cc.get_case(db, first["id"])["results"] == {"r": {"label": "Out", "value": "1.2"}}
    report = cc.compare_cases(first, child)
    assert report["inputs"] == [] and report["results"] == [{"key": "r", "label": "Out", "a": "1.2", "b": "1.3"}]
    assert [c["id"] for c in cc.list_cases(db, calculator="Mud › Weight")] == [child["id"], first["id"]]
    assert cc.list_cases(db, text="mw") and not cc.list_cases(db, text="nothing-like-this")
    with pytest.raises(ValueError):
        cc.save_case(db, calculator="x", name="empty", inputs={}, results={})


def test_the_database_refuses_to_edit_a_stored_case(db):
    from core.authorization import NOBODY, TABLE_POLICY

    case = cc.save_case(db, calculator="c", name="n", inputs={"a": 1}, results={"r": 2})
    assert TABLE_POLICY["calculation_cases"].write == (NOBODY,)
    assert cc.get_case(db, case["id"])["inputs"] == {"a": 1}


# ---- widget capture on a synthetic calculator ---------------------------------------------------
def _calculator_tabs():
    tabs = QTabWidget()
    page = QWidget()
    form = QFormLayout(page)
    page.a, page.b = QDoubleSpinBox(), QDoubleSpinBox()
    for spin, value in ((page.a, 2.0), (page.b, 3.0)):
        spin.setRange(0, 1000)
        spin.setValue(value)
    form.addRow("Length A:", page.a)
    form.addRow("Length B:", page.b)
    page.out = QLabel("--")
    page.out.setStyleSheet("font-weight: bold; border: 1px solid #333;")
    form.addRow("Product:", page.out)
    button = QPushButton("Calculate")
    button.clicked.connect(lambda _=False: page.out.setText(f"{page.a.value() * page.b.value():.2f}"))
    form.addRow(button)
    holder = QWidget()
    inner = QTabWidget(holder)
    QVBoxLayout(holder).addWidget(inner)
    inner.addTab(page, "Area")
    tabs.addTab(holder, "Geometry")
    return tabs, page, button


class _Finder:
    def __init__(self, path):
        self.path = path

    def current_path(self):
        return self.path

    def open_path(self, path):
        self.path = path
        return True


def test_case_bar_saves_reopens_compares_and_reruns(app, db):
    from tabs.calculation_cases_panel import CaseBar, capture_page

    tabs, page, button = _calculator_tabs()
    bar = CaseBar(tabs, _Finder("Geometry › Area"), db=db)
    try:
        assert bar.save_case("too early") is None and "calculate first" in bar.status.text()
        button.click()
        case = bar.save_case("SYN 2x3")
        assert case["inputs"]["QDoubleSpinBox:1"] == {"label": "Length A", "value": 2.0}
        assert case["results"] == {"QLabel:1": {"label": "Product", "value": "6.00"}}
        page.a.setValue(5.0)
        button.click()
        report = bar.compare_current(case["id"])
        assert [d["label"] for d in report["inputs"]] == ["Length A"] and report["results"][0]["b"] == "15.00"
        assert bar.reopen(case["id"]) == [] and page.a.value() == 2.0
        child = bar.rerun(case["id"])
        assert child["parent_id"] == case["id"] and child["results"]["QLabel:1"]["value"] == "6.00"
        assert bar.case_combo.count() == 2
        assert capture_page(page)[0]["QDoubleSpinBox:2"]["value"] == 3.0
    finally:
        bar.deleteLater()
        tabs.deleteLater()
        app.processEvents()


def test_real_w13_quick_calc_case_round_trip(app, db):
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    tab = EngineeringCalculatorTab(db)
    try:
        assert tab.calculator_finder.open_path("Volume › Quick Calc")
        bar = tab.case_bar
        tab.v_od.setValue(5.0)
        tab.v_id.setValue(4.276)
        tab.v_length.setValue(1000.0)
        capacity = tab.v_cap.text()
        assert "0.0178" in capacity or "0.01776" in capacity          # 4.276^2 / 1029.4 = 0.017762 bbl/ft
        case = bar.save_case("SYN 5in DP")
        assert case["calculator"] == "Volume › Quick Calc"
        assert any(v["value"] == capacity for v in case["results"].values())
        tab.v_id.setValue(3.0)
        assert tab.v_cap.text() != capacity
        assert bar.reopen(case["id"]) == [] and tab.v_id.value() == pytest.approx(4.276)
        assert tab.v_cap.text() == capacity
        child = bar.rerun(case["id"])
        assert child is not None and child["parent_id"] == case["id"]
    finally:
        tab.deleteLater()
        app.processEvents()
