"""M78: cross-module workflows end to end through the real widgets and services.

Offscreen Qt, SYNTHETIC databases. Workflow A (survey revision -> tied plan ->
compare) is ``tests/test_m72_survey_ui.py``; workflow D (background DDR import)
is ``tests/test_m71_ddr_background.py``. Here:

B  W13 contract case -> History -> verify -> saved recalculation (lineage) -> report
C  architecture revision -> cement worksheet -> History
E  well delete removes survey, architecture, case and plan records of that well only
F  report quality: escaping, Unicode, page-break rules, statuses in the report
"""
from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtWidgets import QApplication

from core import calculation_cases as cc
from core import calculation_history as ch
from core import directional_plans as dp
from core import survey_revisions as sr
from core import well_architecture as wa
from tests.test_m70_integrity import _open, _seed
from tests.test_m74_well_architecture import ARCH

STATIONS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 500.0, "inc": 0.0, "azi": 0.0}]


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "workflows.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    yield manager, path, _seed(manager)
    manager.close()


def test_b_contract_case_is_verified_recalculated_and_reported_from_history(app, env):
    from tabs.calculation_history_tab import CalculationHistoryTab
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    manager, _path, ids = env
    calc = EngineeringCalculatorTab(manager)
    history = CalculationHistoryTab(manager)
    try:
        calc.current_well_id = ids["A"][0]
        assert calc.calculator_finder.open_path("Volume › Quick Calc")
        calc.v_od.setValue(5.0)
        calc.v_id.setValue(4.276)
        calc.v_length.setValue(1000.0)
        case = calc.case_bar.save_case("SYN workflow B")
        assert case["well_id"] == ids["A"][0]
        history.set_well(ids["A"][0])
        row = next(i for i, e in enumerate(history.entries) if e.record_id == case["id"])
        history.select_rows([row])
        assert "Reproducible: REPRODUCIBLE" in history.statuses_label.text()
        assert history.recalculate()["status"] == "MATCH"
        saved = history.save_recalculation()
        assert saved is not None
        links = cc.source_links(manager, saved["id"])
        assert links[0]["source_id"] == case["id"] and links[0]["link_type"] == "recalculation_of"
        report = history.report_html()
        assert "SYN workflow B" in report and "REPRODUCIBLE" in report and "UNSIGNED" in report
    finally:
        calc.deleteLater()
        history.deleteLater()
        app.processEvents()


def test_c_architecture_worksheet_reaches_history_with_its_revision(app, env):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    manager, _path, ids = env
    tab = WellboreSchematicTab(manager)
    try:
        tab.current_well_id = ids["A"][0]
        panel = tab.architecture_panel
        panel.refresh()
        tab.schematic = wa.to_schematic(ARCH)
        rev = panel.freeze_current()
        panel.table.selectRow(0)
        panel.string_combo.setCurrentText("7 liner")
        panel.cement_selected()
        case = panel.save_cement_case()
        (entry,) = [e for e in ch.load_history(manager, well_id=ids["A"][0]) if e.record_id == case["id"]]
        assert entry.source == "Calculation case" and f"arch rev {rev['revision']}" in entry.name
        state = ch.entry_status(entry)
        assert state["readable"] == "READABLE" and state["reproducible"] == "NOT REPRODUCIBLE"   # no contract
    finally:
        tab.deleteLater()
        app.processEvents()


def test_e_well_delete_removes_every_new_record_of_that_well_only(env):
    manager, path, ids = env
    counts = {}
    for code in ("A", "B"):
        well, bore = ids[code]
        survey = sr.save_revision(manager, well, STATIONS, depth_datum="RKB", wellbore_id=bore, azimuth_reference="true")
        wa.save_revision(manager, well, ARCH, wellbore_id=bore, survey_revision_id=survey["id"])
        cc.save_case(manager, calculator="x", name=f"SYN {code}", inputs={"a": 1}, results={"r": 1}, well_id=well)
        dp.save_plan(manager, well_id=well, name=f"SYN plan {code}", inputs=dp.plan_inputs(
            [{"type": "hold", "length": 500.0}]))
    tables = ("survey_revisions", "well_architecture_revisions", "calculation_cases", "directional_plan_revisions")
    with sqlite3.connect(path) as connection:
        for table in tables:
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    manager.delete_well(ids["A"][0])
    with sqlite3.connect(path) as connection:
        for table in tables:
            left = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            mine = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE well_id=?", (ids["A"][0],)).fetchone()[0]
            assert (mine, left) == (0, counts[table] - 1), table      # the other well keeps its record


def test_f_reports_escape_markup_keep_unicode_and_carry_statuses(env):
    manager, _path, ids = env
    name = "<b>SYN</b> & 'q' — ΔP 深度 عمق"
    case = cc.save_case(manager, calculator="x", name=name, inputs={"<i>k</i>": {"label": "x", "value": "<v>"}},
                        results={"r": {"label": "z", "value": 1.5}}, well_id=ids["A"][0])
    (entry,) = [e for e in ch.load_history(manager) if e.record_id == case["id"]]
    report = ch.render_entry_report(entry, well_label=ch.well_label(manager, ids["A"][0]))
    assert "<b>SYN</b>" not in report and "&lt;b&gt;SYN&lt;/b&gt; &amp;" in report
    assert "ΔP 深度 عمق" in report and "&lt;v&gt;" in report and "<i>k</i>" not in report
    assert "page-break-inside:avoid" in report and "Reproducible" in report and "charset='utf-8'" in report
