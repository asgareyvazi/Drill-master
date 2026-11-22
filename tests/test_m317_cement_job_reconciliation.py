"""M317 (M280): a recorded cement job reconciled with a frozen architecture revision (SYNTHETIC, WORKSHEET).

Hand-computed expectations (published oilfield capacities, not the engine):
annulus 12.25 x 9.625 in = (12.25² − 9.625²)/1029.4 bbl/ft = 0.0557819 bbl/ft = 0.183011 bbl/m;
9-5/8 in casing ID 8.681 in = 8.681²/1029.4 bbl/ft; pumped = sacks × ft³/sk ÷ 5.6146 ft³/bbl.
"""
from __future__ import annotations

import datetime as dt

import pytest

from core import calculation_cases as cc
from core import cement_job_reconciliation as cj
from core import well_architecture as wa
from core.database import CementReport
from synthetic_operations import build_synthetic_operations, make_file_database
from test_m74_well_architecture import ARCH

ANNULUS_BBL_M = (12.25 ** 2 - 9.625 ** 2) / 1029.4 * 3.28084
CAPACITY_TO_SHOE = 8.681 ** 2 / 1029.4 * 1000 * 3.28084


@pytest.fixture
def world(tmp_path):
    db = make_file_database(tmp_path / "m317.db")
    ids = build_synthetic_operations(db)
    rev = wa.save_revision(db, ids["dev"], ARCH)
    yield db, ids, rev
    db.engine.dispose()


def _job(db, well_id, **values):
    base = {"cement_volume": 500.0, "slurry_yield": 1.15, "top_of_cement": 400.0, "bottom_of_cement": 1000.0,
            "displacement_volume": 238.0, "slurry_density": 118.0}
    base.update(values)
    with db.session_scope() as session:
        row = CementReport(well_id=well_id, report_date=dt.date(2026, 1, 5), report_name="SYN job", **base)
        session.add(row)
        session.flush()
        return row.id


def test_reconciles_pumped_volume_gauge_annulus_and_displacement(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    assert result["status"] == "COMPUTED" and result["label"] == cj.LABEL
    assert result["pumped_bbl"] == pytest.approx(500 * 1.15 / 5.6146, rel=1e-9)
    assert result["gauge_bbl"] == pytest.approx(ANNULUS_BBL_M * 600, rel=1e-6)
    assert result["implied_excess_pct"] == pytest.approx((500 * 1.15 / 5.6146 / (ANNULUS_BBL_M * 600) - 1) * 100,
                                                         rel=1e-6)
    assert [(i["top_md"], i["bottom_md"], i["outer"]) for i in result["intervals"]] == [(400.0, 1000.0, "open hole")]
    assert result["architecture_interval"] == {"top_md": 500.0, "bottom_md": 1000.0}
    assert result["toc_difference_m"] == -100.0
    assert result["displacement"]["capacity_to_shoe_bbl"] == pytest.approx(CAPACITY_TO_SHOE, abs=0.001)
    assert result["displacement"]["status"] == cj.WITHIN
    assert "upper bound" in result["displacement"]["reason"]


def test_over_displacement_is_flagged(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], displacement_volume=300.0), rev["id"], "9-5/8 csg",
                          yield_unit="ft3/sk")
    assert result["displacement"]["status"] == cj.OVER_CAPACITY


def test_yield_unit_is_never_assumed(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg")
    assert result["pumped_bbl"] is None and result["implied_excess_pct"] is None
    assert any("yield unit" in n for n in result["notes"])
    assert result["gauge_bbl"] is not None                       # the geometry part still works
    with pytest.raises(cj.ReconciliationError):
        cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg", yield_unit="kg/sk")   # a mass basis


@pytest.mark.parametrize("values, note", [
    ({"top_of_cement": None}, "neither is inferred"),
    ({"bottom_of_cement": None}, "neither is inferred"),
    ({"top_of_cement": 1000.0, "bottom_of_cement": 900.0}, "is not below"),
])
def test_missing_or_inverted_toc_boc_is_never_inferred(world, values, note):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], **values), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    assert result["gauge_bbl"] is None and result["intervals"] == []
    assert any(note in n for n in result["notes"])
    assert result["pumped_bbl"] is not None


def test_surface_toc_zero_is_a_real_depth(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], top_of_cement=0.0), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    assert result["job"]["toc_m"] == 0.0 and result["gauge_bbl"] == pytest.approx(ANNULUS_BBL_M * 1000, rel=1e-6)


def test_declared_caliper_changes_the_open_hole_size_only(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg", yield_unit="ft3/sk", caliper_in=13.0)
    expected = (13.0 ** 2 - 9.625 ** 2) / 1029.4 * 3.28084 * 600
    assert result["gauge_bbl"] == pytest.approx(expected, rel=1e-6)
    assert result["intervals"][0]["outer_source"] == "declared average caliper"


def test_liner_displacement_is_not_applicable(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], top_of_cement=900.0, bottom_of_cement=2000.0), rev["id"],
                          "7 liner", yield_unit="ft3/sk")
    assert result["displacement"]["status"] == cj.NOT_APPLICABLE
    cased = [i for i in result["intervals"] if i["outer"] == "9-5/8 csg"]
    assert cased and cased[0]["outer_id_in"] == 8.681                 # cased overlap uses the outer string's ID


def test_other_well_and_unknown_string_are_refused(world):
    db, ids, rev = world
    with pytest.raises(cj.ReconciliationError):
        cj.reconcile(db, _job(db, ids["qa"]), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    with pytest.raises(cj.ReconciliationError):
        cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "13-3/8 csg", yield_unit="ft3/sk")
    with pytest.raises(LookupError):
        cj.reconcile(db, 99999, rev["id"], "9-5/8 csg")


def test_nothing_recorded_is_not_computed_and_cannot_be_saved(world):
    db, ids, rev = world
    job = _job(db, ids["dev"], cement_volume=None, top_of_cement=None, displacement_volume=None)
    result = cj.reconcile(db, job, rev["id"], "7 liner", yield_unit="ft3/sk")
    assert result["status"] == "NOT_COMPUTED" and result["displacement"]["status"] == cj.NOT_APPLICABLE
    assert result["pumped_bbl"] is None and result["gauge_bbl"] is None
    with pytest.raises(ValueError):
        cj.save_case(db, result)


def test_save_stores_a_case_linked_to_the_cement_report_and_changes_nothing(world):
    db, ids, rev = world
    job_id = _job(db, ids["dev"])
    before = cj.recorded_job(db, job_id)
    result = cj.reconcile(db, job_id, rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    case = cj.save_case(db, result)
    stored = cc.get_case(db, case["id"])
    assert stored["method_version"] == cj.METHOD_VERSION
    assert stored["inputs"]["yield_unit"]["source"] == "DECLARED"
    assert stored["results"]["displacement_check"]["value"] == cj.WITHIN
    link = cc.source_links(db, case["id"])[0]
    assert (link["source_table"], link["source_id"]) == ("cement_reports", job_id)
    assert cj.recorded_job(db, job_id) == before
    assert wa.get_revision(db, rev["id"])["components_sha256"] == rev["components_sha256"]
    from core import calculation_history as ch
    entry = [e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"]][0]
    assert ch.entry_status(entry)["reproducible"] == "REPRODUCIBLE"       # M328 replay adapter
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"


def test_summary_states_unknowns_as_unknown(world):
    db, ids, rev = world
    lines = cj.summary_lines(cj.reconcile(db, _job(db, ids["dev"], top_of_cement=None), rev["id"], "9-5/8 csg"))
    text = " ".join(lines)
    assert lines[0].startswith("WORKSHEET") and "TOC unknown" in text and "Pumped slurry: unknown" in text
    assert "0.00 bbl" not in text
    assert len(cj.list_jobs(db, ids["dev"])) == 1


# ---- UI: W3b schematic -> Architecture page -> "Reconcile recorded job" ----------------------------------------
def test_architecture_panel_reconciles_and_saves_through_the_buttons(world):
    from PySide6 import QtWidgets

    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    db, ids, _rev = world
    job_id = _job(db, ids["dev"])
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = WellboreSchematicTab(db)
    try:
        tab.current_well_id = ids["dev"]
        panel = tab.architecture_panel
        panel.refresh()
        assert panel.job_combo.count() == 1 and panel.job_combo.currentData() == job_id
        panel.table.selectRow(0)
        panel.string_combo.setCurrentText("9-5/8 csg")
        assert panel.reconcile_btn.isEnabled() and not panel.save_reconcile_btn.isEnabled()
        panel.reconcile_btn.click()                                # yield unit not declared
        assert "Pumped slurry: unknown" in panel.status.text() and cj.LABEL in panel.status.text()
        panel.yield_unit_combo.setCurrentIndex(panel.yield_unit_combo.findData("ft3/sk"))
        panel.reconcile_btn.click()
        assert "Displacement: WITHIN_UPPER_BOUND" in panel.status.text()
        assert panel.save_reconcile_btn.isEnabled()
        panel.save_reconcile_btn.click()
        assert "saved as calculation case" in panel.status.text() and not panel.save_reconcile_btn.isEnabled()
        cases = cc.list_cases(db, calculator="Cement job reconciliation", well_id=ids["dev"])
        assert len(cases) == 1
    finally:
        tab.deleteLater()
        app.processEvents()
