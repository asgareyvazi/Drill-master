"""M67: unified calculation history, recalculate-and-verify, Report Center.

Temporary SQLite database with synthetic data; real MSE engine runs saved by
the real repository. Independent hand value (Teale 1965):
MSE = 4 WOB / (pi d^2) + 480 T N / (d^2 ROP) = 440.58 + 127557.09 = 127997.67 psi
for WOB 25000 lbf, T 8000 ft-lbf, N 120 rpm, ROP 50 ft/h, d 8.5 in.
The tab test runs offscreen (not Windows desktop testing).
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from core import calculation_cases as cc
from core import calculation_history as ch
from core import directional_plans as dp

INPUTS = dict(wob_lbf=25000.0, rpm=120.0, torque_ft_lbf=8000.0, rop_ft_hr=50.0, bit_diameter_in=8.5)
HAND_MSE = 4 * 25000 / (math.pi * 8.5 ** 2) + 480 * 8000 * 120 / (8.5 ** 2 * 50)


@pytest.fixture
def seeded():
    from synthetic_operations import make_file_database
    from core.database import Company, Project, Well
    from core.engineering.engines.mse import MSEEngine
    from core.repositories.mse_repository import MSECalculationRepository

    db = make_file_database(Path(tempfile.mkdtemp(prefix="m67-history-")) / "history.db")
    with db.session_scope() as session:
        company = Company(name="SYN CO", code="SYN")
        session.add(company)
        session.flush()
        project = Project(name="SYN FIELD", code="SYNF", company_id=company.id)
        session.add(project)
        session.flush()
        wells = [Well(name=f"SYN-H-0{i}", code=f"SYN-H-0{i}", project_id=project.id) for i in (1, 2)]
        session.add_all(wells)
        session.flush()
        well_ids = [w.id for w in wells]
    repo = MSECalculationRepository(db)
    good = MSEEngine.calculate(**INPUTS)
    ids = {"mse": repo.save_run(inputs=INPUTS, result_values=good.values, method=MSEEngine.METHOD,
                                label="SYN MSE base", well_id=well_ids[0])}
    tampered = dict(good.values, mse_psi=good.values["mse_psi"] + 500.0)
    ids["mse_bad"] = repo.save_run(inputs=dict(INPUTS, rpm=140.0), result_values=tampered,
                                   method=MSEEngine.METHOD, label="SYN MSE stored-wrong", well_id=well_ids[0])
    ids["case"] = cc.save_case(db, calculator="Mud › Weight", name="SYN case", inputs={"a": 1},
                               results={"r": 2}, well_id=well_ids[0])["id"]
    ids["plan"] = dp.save_plan(db, well_id=well_ids[0], name="SYN plan", inputs=dp.plan_inputs(
        [{"type": "hold", "length": 500.0}, {"type": "curve", "inc": 30.0, "azi": 135.0, "dls": 3.0},
         {"type": "hold_to_tvd", "tvd": 1500.0}]))["id"]
    ids["other_well_case"] = cc.save_case(db, calculator="x", name="SYN other", inputs={"a": 1}, results={"r": 1},
                                          well_id=well_ids[1])["id"]
    yield db, well_ids, ids
    db.engine.dispose()


def _entry(entries, table, record_id):
    return next(e for e in entries if e.table == table and e.record_id == record_id)


def test_history_unifies_sources_and_filters(seeded):
    db, wells, ids = seeded
    entries = ch.load_history(db, well_id=wells[0])
    assert {e.source for e in entries} == {"MSE", "Calculation case", "Directional plan"}
    assert len(entries) == 4 and all(e.well_id == wells[0] for e in entries)
    mse = _entry(entries, "mse_calculations", ids["mse"])
    assert mse.results["mse_psi"] == pytest.approx(HAND_MSE, rel=1e-6)     # independent Teale hand value
    assert mse.version.startswith("snapshot schema v") and mse.scope == "SCREENING"
    plan = _entry(entries, "directional_plan_revisions", ids["plan"])
    assert plan.results["td_md"] == pytest.approx(1623.9032011, abs=1e-6)  # M55 golden J-profile
    assert [e.source for e in ch.load_history(db, sources=["MSE"])] == ["MSE", "MSE"]
    assert [e.name for e in ch.load_history(db, text="stored-wrong")] == ["SYN MSE stored-wrong"]
    assert len(ch.load_history(db)) == 5


def test_recalculation_verifies_without_touching_the_original(seeded):
    db, wells, ids = seeded
    entries = ch.load_history(db, well_id=wells[0])
    ok = ch.recalculate_entry(_entry(entries, "mse_calculations", ids["mse"]))
    assert ok["status"] == "MATCH" and ok["method_matches"] is True
    bad_entry = _entry(entries, "mse_calculations", ids["mse_bad"])
    bad = ch.recalculate_entry(bad_entry)
    assert bad["status"] == "DIFFERENT"
    stored = ch.save_recalculation(db, bad_entry, bad)
    assert stored["calculator"] == "MSE recalculation" and "verification DIFFERENT" in stored["note"]
    again = _entry(ch.load_history(db, well_id=wells[0]), "mse_calculations", ids["mse_bad"])
    assert again.results["mse_psi"] == bad_entry.results["mse_psi"]          # original unchanged
    plan = ch.recalculate_entry(_entry(entries, "directional_plan_revisions", ids["plan"]))
    assert plan["status"] == "MATCH" and plan["method_matches"] is True
    none = ch.recalculate_entry(_entry(entries, "calculation_cases", ids["case"]))
    assert none["status"] == "NOT_REPRODUCIBLE" and "reopen it in its calculator" in none["detail"]
    with pytest.raises(ValueError):
        ch.save_recalculation(db, _entry(entries, "calculation_cases", ids["case"]), none)


def test_compare_csv_and_reports(seeded, tmp_path):
    db, wells, ids = seeded
    entries = ch.load_history(db, well_id=wells[0])
    a, b = _entry(entries, "mse_calculations", ids["mse"]), _entry(entries, "mse_calculations", ids["mse_bad"])
    report = ch.compare_entries(a, b)
    assert ("parameters.rpm", 120.0, 140.0) in report["inputs"] and report["same_version"]
    html = ch.render_entry_report(a, well_label="SYN-H-01")
    for needle in ("SYN MSE base", "Method version", "snapshot schema v", "UNSIGNED", "not validated", "SYN-H-01"):
        assert needle in html
    assert "parameters.rpm" in ch.render_comparison_report(a, b)
    out = tmp_path / "history.csv"
    assert ch.export_history_csv(entries, str(out)) == 4
    assert out.read_text(encoding="utf-8").splitlines()[0].startswith("source,id,well_id,name")


def test_history_tab_compares_recalculates_and_exports_pdf(seeded, tmp_path):
    from PySide6.QtWidgets import QApplication
    from tabs.calculation_history_tab import CalculationHistoryTab

    app = QApplication.instance() or QApplication([])
    db, wells, ids = seeded
    tab = CalculationHistoryTab(db)
    try:
        tab.set_well(wells[0])
        assert tab.table.rowCount() == 4 and tab.layoutDirection().name == "LeftToRight"
        mse_rows = [i for i, e in enumerate(tab.entries) if e.table == "mse_calculations"]
        tab.select_rows(mse_rows)
        assert tab.compare_btn.isEnabled() and tab.compare()["inputs"]
        tab.select_rows([mse_rows[0]])
        outcome = tab.recalculate()
        assert outcome["status"] in ("MATCH", "DIFFERENT") and tab.save_recalc_btn.isEnabled()
        pdf = tmp_path / "report.pdf"
        assert tab.export_report(str(pdf)) and pdf.read_bytes()[:4] == b"%PDF"
        case = tab.save_recalculation()
        assert case is not None and tab.table.rowCount() == 5
        tab.well_only.setChecked(False)
        assert tab.table.rowCount() == 6
    finally:
        tab.deleteLater()
        app.processEvents()
