"""M83: one selection lifecycle across every DrillTabBase tab (real MainWindow, offscreen, SYNTHETIC DB).

A well switch must not leave the previous well's identifiers on any tab, a
clear (the selected record was deleted) must leave an empty state with clean
edit baselines, deleting the company/project holding the selected well clears
the selection, and background work can detect a stale context via the token.
Offscreen Qt on Linux; not Windows desktop acceptance.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QPlainTextEdit, QTableWidget, QTextEdit, QTreeWidget
from sqlalchemy import text

from core.base_tab import DrillTabBase
from core.selection_manager import SelectionManager
from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)

ALPHA = ("SYN-ALPHA-01", "SYN-A1", "SYN RIG 1", "SYN FIELD", "SYN 12 1/4")
PORTFOLIO = {"HomeTab"}   # the Home dashboard lists every well by design; it is not selection-scoped


def _values(widget, cls):
    if cls in (QLineEdit, QLabel):
        return [widget.text()]
    if cls is QComboBox:
        return [widget.currentText()]
    if cls in (QTextEdit, QPlainTextEdit):
        return [widget.toPlainText()[:5000]]
    if cls is QTableWidget:
        return [widget.item(r, c).text() for r in range(min(widget.rowCount(), 300))
                for c in range(widget.columnCount()) if widget.item(r, c)]
    out, stack = [], [widget.invisibleRootItem()]
    while stack:
        item = stack.pop()
        out += [item.text(c) for c in range(widget.columnCount())]
        stack += [item.child(i) for i in range(item.childCount())]
    return out


def _leaks(tab, marks=ALPHA):
    found = set()
    for cls in (QLineEdit, QLabel, QComboBox, QTableWidget, QTreeWidget, QTextEdit, QPlainTextEdit):
        for widget in tab.findChildren(cls):
            found |= {m for value in _values(widget, cls) for m in marks if m in (value or "")}
    return found


@pytest.fixture
def no_prompts(monkeypatch):
    """Daily Report asks whether to create a section for a well without one; answer No."""
    import tabs.w2_Daily_Report as w2
    monkeypatch.setattr(w2.QMessageBox, "question", staticmethod(lambda *a, **k: w2.QMessageBox.No))


def _scoped_tabs(win):
    tabs = [win.tab_widget.widget(i) for i in range(win.tab_widget.count())]
    return [t for t in tabs if isinstance(t, DrillTabBase) and type(t).__name__ not in PORTFOLIO]


def _dirty_sections(tab):
    from PySide6.QtWidgets import QWidget
    return sorted({f"{type(owner).__name__}:{section.name}" for owner in [tab, *tab.findChildren(QWidget)]
                   for section in getattr(owner, "_tracked_edit_sections", ()) if section.dirty})


def _visit(win, tabs, seconds=0.35):
    for tab in tabs:
        win.tab_widget.setCurrentWidget(tab)
        _pump(seconds)


def test_context_token_changes_on_every_selection_event():
    sel = SelectionManager()
    sel.clear()
    token = sel.context_token()
    sel.select_well(910001, {"id": 910001})
    assert not sel.is_current(token)
    token = sel.context_token()
    sel.select_well(910001, {"id": 910001}, force=True)      # a forced refresh is a new context too
    assert not sel.is_current(token)
    token = sel.context_token()
    sel.clear()
    assert not sel.is_current(token) and sel.is_current(sel.context_token())


def test_switching_wells_leaves_no_identifier_of_the_previous_well(window, no_prompts):  # noqa: F811
    win, _db, ids = window
    tabs = _scoped_tabs(win)
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    _visit(win, tabs)
    shown = {type(t).__name__ for t in tabs if _leaks(t)}
    assert len(shown) >= 10, shown                              # the probe sees the well where it is shown
    viewed_only = {type(t).__name__: _dirty_sections(t) for t in tabs if _dirty_sections(t)}
    assert viewed_only == {}, viewed_only                       # viewing a well is not an edit (W3c cement form)
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.4)
    _visit(win, tabs)
    stale = {type(t).__name__: sorted(_leaks(t)) for t in tabs if _leaks(t)}
    assert stale == {}, stale


def test_clear_leaves_an_empty_state_and_clean_edit_baselines(window, no_prompts):  # noqa: F811
    win, _db, ids = window
    tabs = _scoped_tabs(win)
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    _visit(win, tabs)
    SelectionManager().clear()
    _pump(0.3)
    _visit(win, tabs, 0.25)
    stale = {type(t).__name__: sorted(_leaks(t)) for t in tabs if _leaks(t)}
    assert stale == {}, stale
    assert {type(t).__name__: _dirty_sections(t) for t in tabs if _dirty_sections(t)} == {}
    assert win.well_info_tab.well_name.text() == "" and win.well_info_tab.current_well is None
    assert win.engineering_calc_tab.current_well_id is None


def test_section_forms_do_not_carry_values_to_another_well(window, no_prompts):  # noqa: F811
    win, _db, ids = window
    w3c = win.section_data_tab
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    win.tab_widget.setCurrentWidget(w3c)
    _pump(0.4)
    w3c.cement_tab.report_name.setText("SYN cement job A")      # value shown for well A
    w3c.cement_tab.top_of_cement.setValue(1234.0)
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    win.tab_widget.setCurrentWidget(w3c)
    _pump(0.4)
    assert w3c.cement_tab.report_name.text() == "" and w3c.cement_tab.top_of_cement.value() != 1234.0
    assert _dirty_sections(w3c) == []


def test_deleting_the_project_of_the_selected_well_clears_the_selection(window, monkeypatch):  # noqa: F811
    win, db, ids = window
    import main_window
    with db.session_scope() as session:
        project = session.execute(text("SELECT id FROM projects WHERE code='SYN-PW'")).scalar()
    win.navigate_to({"type": "well", "id": ids["twin_2"]})
    _pump(0.4)
    assert SelectionManager().current_well_id == ids["twin_2"]
    monkeypatch.setattr(main_window.QMessageBox, "question", staticmethod(lambda *a, **k: main_window.QMessageBox.Yes))
    win._delete_project(project)
    _pump(0.4)
    assert db.get_well_by_id(ids["twin_2"]) is None
    assert SelectionManager().current_well_id is None
    assert win.well_info_tab.current_well is None


@pytest.mark.parametrize("name", ["w1_well_info", "w2_Daily_Report", "w3_drilling_report", "w3b_wellbore_schematic_tab",
                                  "w5_Equipment_Widget", "w6_Trajectory_Widget", "w7_logistics_Widget",
                                  "w9_Services_Widget", "w10_Planning_Widget", "w11_Export",
                                  "w13_Engineering_Calculator"])
def test_context_bound_tabs_define_their_empty_state(name):
    import importlib
    import inspect
    module = importlib.import_module(f"tabs.{name}")
    tabs = [c for _n, c in inspect.getmembers(module, inspect.isclass)
            if issubclass(c, DrillTabBase) and c is not DrillTabBase and c.__module__ == module.__name__]
    assert tabs and all("on_selection_cleared" in vars(c) for c in tabs), name
