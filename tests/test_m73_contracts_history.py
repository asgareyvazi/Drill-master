"""M73: calculator contracts, reproducibility, unit-safe comparison, history paging.

Offscreen Qt for the W13 and history-tab tests; synthetic databases only.
The capacity reference is computed by hand here (ID^2 / 1029.4 bbl/ft), not
by the engine under test.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from core import calculation_cases as cc
from core import calculation_history as ch
from core import calculator_contracts as contracts

FT_PER_M = 3.28084


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db():
    from synthetic_operations import make_file_database
    from core.database import Company, Project, Well

    manager = make_file_database(Path(tempfile.mkdtemp(prefix="m73-")) / "m73.db")
    with manager.session_scope() as session:
        company = Company(name="SYN CO", code="SYN")
        session.add(company)
        session.flush()
        project = Project(name="SYN FIELD", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="SYN-C-01", code="SYN-C-01", project_id=project.id)
        session.add(well)
        session.flush()
        manager.test_well_id = well.id
    yield manager
    manager.engine.dispose()


def _entry(db, case_id):
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


def _quick_case(db, *, od=5.0, inner=4.276, length=1000.0, capacity=None, version=None):
    cap = inner ** 2 / 1029.4 * FT_PER_M if capacity is None else capacity
    inputs = {"QDoubleSpinBox:1": {"label": "OD", "value": od}, "QDoubleSpinBox:2": {"label": "ID", "value": inner},
              "QDoubleSpinBox:3": {"label": "Length", "value": length}}
    results = {"QLabel:1": {"label": "Capacity", "value": f"{cap:.5f} bbl/m  |  {cap / FT_PER_M:.5f} bbl/ft"}}
    inputs, results, missing = contracts.annotate(contracts.QUICK_CALC_V1, inputs, results)
    assert missing == []
    return cc.save_case(db, calculator=contracts.QUICK_CALC_V1.calculator, name="SYN quick", inputs=inputs,
                        results=results, method=contracts.QUICK_CALC_V1.method_id,
                        method_version=version or contracts.QUICK_CALC_V1.method_version)


# ---- contracts --------------------------------------------------------------------------------------
def test_the_quick_calc_contract_reproduces_an_independent_reference():
    current = contracts.QUICK_CALC_V1.recalculate({"od": 5.0, "id": 4.276, "length": 1000.0})
    assert current["capacity"] / FT_PER_M == pytest.approx(4.276 ** 2 / 1029.4, rel=1e-9)     # 0.017762 bbl/ft
    assert current["displacement"] / FT_PER_M == pytest.approx((5.0 ** 2 - 4.276 ** 2) / 1029.4, rel=1e-9)
    assert current["volume"] == pytest.approx(current["capacity"] * 1000.0)
    assert contracts.QUICK_CALC_V1.recalculate({"od": 5.0, "id": 4.276, "length": 0.0})["volume"] is None
    with pytest.raises(ValueError):
        contracts.QUICK_CALC_V1.recalculate({"od": 4.0, "id": 4.276, "length": 10.0})


def test_contract_cases_verify_match_different_unavailable_and_unreadable(db, monkeypatch):
    good = _quick_case(db)
    first = ch.recalculate_entry(_entry(db, good["id"]))
    assert first["status"] == "MATCH" and first["not_compared"] == ["displacement", "volume", "metal_volume"]
    wrong = _quick_case(db, capacity=0.07)
    outcome = ch.recalculate_entry(_entry(db, wrong["id"]))
    assert outcome["status"] == "DIFFERENT" and outcome["differences"][0]["field_id"] == "capacity"
    assert outcome["differences"][0]["tolerance"] == pytest.approx(5e-6)      # half the last displayed decimal
    legacy = cc.save_case(db, calculator=contracts.QUICK_CALC_V1.calculator, name="SYN legacy",
                          inputs={"k": {"label": "OD", "value": 5.0}}, results={"r": {"label": "Capacity", "value": "1"}})
    out = ch.recalculate_entry(_entry(db, legacy["id"]))
    assert out["status"] == "NOT_REPRODUCIBLE" and "without a method version" in out["detail"]
    monkeypatch.setitem(contracts.AVAILABLE_METHODS, contracts.QUICK_CALC_V1.method_id, ())
    out = ch.recalculate_entry(_entry(db, good["id"]))
    assert out["status"] == "NOT_REPRODUCIBLE" and "no longer available" in out["detail"]
    monkeypatch.undo()
    broken = _quick_case(db, inner=6.0)          # ID > OD: the method refuses, nothing is guessed
    assert ch.recalculate_entry(_entry(db, broken["id"]))["status"] == "UNREADABLE"


def test_entry_status_answers_readable_comparable_and_reproducible_separately(db):
    good = _quick_case(db)
    state = ch.entry_status(_entry(db, good["id"]))
    assert (state["readable"], state["comparable"], state["reproducible"]) == ("READABLE", "COMPARABLE",
                                                                                 "REPRODUCIBLE")
    text_only = cc.save_case(db, calculator="Mud › Notes", name="SYN text", inputs={"a": {"label": "x", "value": "y"}},
                             results={"r": {"label": "z", "value": "n/a"}})
    state = ch.entry_status(_entry(db, text_only["id"]))
    assert state["comparable"] == "NOT COMPARABLE" and state["reproducible"] == "NOT REPRODUCIBLE"


def test_entry_status_reports_records_whose_stored_data_cannot_be_read(db):
    """M97 (mutation gap): the UNREADABLE answer itself was never asserted."""
    from dataclasses import replace
    entry = _entry(db, _quick_case(db)["id"])
    for broken in (replace(entry, inputs={}), replace(entry, results="not a mapping"),
                   replace(entry, inputs="not a mapping")):
        state = ch.entry_status(broken)
        assert state["readable"] == "UNREADABLE", broken
    assert ch.entry_status(entry)["readable"] == "READABLE"


def test_numeric_differences_are_unit_safe_and_split_inputs_from_results(db):
    a, b = _quick_case(db), _quick_case(db, inner=4.0)
    numeric = ch.numeric_differences(_entry(db, a["id"]), _entry(db, b["id"]))
    (diff,) = numeric["inputs"]
    assert diff["status"] == "DIFFERENT" and diff["unit"] == "in" and diff["delta"] == pytest.approx(-0.276)
    assert numeric["results"][0]["key"] == "QLabel:1" and numeric["results"][0]["unit"] == "bbl/m"
    other = cc.save_case(db, calculator="x", name="SYN ft", inputs={"QDoubleSpinBox:3": {"value": 3280.84, "unit": "ft"}},
                         results={})
    mixed = ch.numeric_differences(_entry(db, a["id"]), _entry(db, other["id"]))
    (m,) = [d for d in mixed["inputs"] if d["key"] == "QDoubleSpinBox:3"]
    assert m["status"] == "UNIT MISMATCH" and (m["unit_a"], m["unit_b"]) == ("m", "ft")   # never converted


# ---- paging and database-side filters ------------------------------------------------------------
def test_history_pages_are_newest_first_without_gaps_or_duplicates(db):
    ids = [cc.save_case(db, calculator="x", name=f"SYN page {i}", inputs={"a": i}, results={"r": i})["id"]
           for i in range(7)]
    assert ch.count_history(db) == 7
    pages = [ch.load_history(db, limit=3, offset=o) for o in (0, 3, 6)]
    assert [len(p) for p in pages] == [3, 3, 1]
    assert [e.record_id for p in pages for e in p] == list(reversed(ids))
    assert ch.count_history(db, text="page 3") == 1 and ch.load_history(db, text="PAGE 3")[0].record_id == ids[3]
    fifth = next(e for e in pages[0] if e.record_id == ids[5]).created_at     # cases are immutable: stored times
    assert ch.count_history(db, since=fifth) == 2 and ch.count_history(db, until=fifth - timedelta(microseconds=1)) <= 5
    assert ch.count_history(db, sources=["Directional plan"]) == 0


def test_history_tab_pages_and_resets_on_filter_change(app, db, monkeypatch):
    import tabs.calculation_history_tab as tab_module

    for i in range(5):
        cc.save_case(db, calculator="x", name=f"SYN tab {i}", inputs={"a": i}, results={"r": i})
    monkeypatch.setattr(tab_module, "PAGE_SIZE", 2)
    tab = tab_module.CalculationHistoryTab(db)
    try:
        tab.well_only.setChecked(False)
        tab.refresh()
        assert (tab.total, len(tab.entries), tab.page_label.text()) == (5, 2, "Page 1 of 3")
        assert not tab.prev_btn.isEnabled() and tab.next_btn.isEnabled()
        tab.go_page(2)
        assert len(tab.entries) == 1 and tab.page_label.text() == "Page 3 of 3" and not tab.next_btn.isEnabled()
        tab.text_edit.setText("tab 1")
        tab._refresh_clicked()
        assert (tab.page, tab.total, tab.page_label.text()) == (0, 1, "Page 1 of 1")
        tab.select_rows([0])
        assert "Reproducible: NOT REPRODUCIBLE" in tab.statuses_label.text()
    finally:
        tab.deleteLater()
        app.processEvents()


# ---- the real W13 calculator --------------------------------------------------------------------
def test_real_w13_quick_calc_saves_a_versioned_case_that_verifies(app, db):
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    tab = EngineeringCalculatorTab(db)
    try:
        assert tab.calculator_finder.open_path("Volume › Quick Calc")
        tab.v_od.setValue(5.0)
        tab.v_id.setValue(4.276)
        tab.v_length.setValue(1000.0)
        case = tab.case_bar.save_case("SYN contract")
        assert case["method_version"] == contracts.QUICK_CALC.method_version and case["note"] == ""
        assert {v.get("field_id") for v in case["inputs"].values()} >= {"od", "id", "length"}
        assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "MATCH"
        child = tab.case_bar.rerun(case["id"])
        assert child["method_version"] == case["method_version"] and "changed" not in child["note"]
    finally:
        tab.deleteLater()
        app.processEvents()
