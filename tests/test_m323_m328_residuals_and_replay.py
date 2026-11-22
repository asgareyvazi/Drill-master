"""M323 residual repairs (A-1, A-3, A-4, summary zeros), M331 yield-unit registry and M328 History replay.

All data is SYNTHETIC. Hand values are stated next to each assertion; none is taken from the engine under test.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt

import pytest

from core import architecture_diff as ad
from core import calculation_cases as cc
from core import calculation_history as ch
from core import cement_job_reconciliation as cj
from core import history_replay as hr
from core import well_architecture as wa
from core.database import CasingCalculationRecord, CementReport
from synthetic_operations import build_synthetic_operations, make_file_database
from test_m74_well_architecture import ARCH


@pytest.fixture
def world(tmp_path):
    db = make_file_database(tmp_path / "m323.db")
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


def _entry(db, case_id):
    return [e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id][0]


# ---- A-1: the architecture diff lists casing-design runs pinned to the older revision ------------------------
def test_a1_architecture_diff_lists_casing_runs_and_reconciliations_pinned_to_the_older_revision(world):
    db, ids, rev = world
    with db.session_scope() as session:
        row = CasingCalculationRecord(well_id=ids["dev"], label="SYN casing run", method="synthetic",
                                      input_snapshot_json={"source": {"architecture_revision_id": rev["id"]}})
        session.add(row)
        session.flush()
        casing_id = row.id
    recon = cj.save_case(db, cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg",
                                                    yield_unit="ft3/sk"))
    newer = wa.save_revision(db, ids["dev"], ARCH[:-1], parent_id=rev["id"])
    result = ad.compare_revisions(db, rev["id"], newer["id"])
    keys = [p["key"] for p in result["pinned_cases"]]
    assert keys == [f"casing_calculations:{casing_id}", f"calculation_cases:{recon['id']}"]
    assert result["pinned_cases"][0]["name"] == "SYN casing run"
    assert f"casing_calculations:{casing_id}" in ad.summary_lines(result)[-1]


# ---- A-3 / A-4 / summary zeros -----------------------------------------------------------------------------
def test_a3_a_displacement_below_capacity_is_an_upper_bound_statement_not_consistency(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    assert result["displacement"]["status"] == cj.WITHIN == "WITHIN_UPPER_BOUND"
    assert "under-displacement cannot be judged" in result["displacement"]["reason"]
    assert not hasattr(cj, "CONSISTENT")


@pytest.mark.parametrize("field, word", [("cement_volume", "sacks"), ("slurry_yield", "yield")])
def test_a4_a_recorded_zero_is_reported_as_recorded_not_as_missing(world, field, word):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], **{field: 0.0}), rev["id"], "9-5/8 csg", yield_unit="ft3/sk")
    assert result["pumped_bbl"] is None
    assert any(f"{word} recorded as 0" in n for n in result["notes"]), result["notes"]
    assert not any("must both be recorded" in n for n in result["notes"])


def test_summary_shows_a_zero_toc_difference_instead_of_hiding_it(world):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], top_of_cement=500.0), rev["id"], "9-5/8 csg",
                          yield_unit="ft3/sk")            # ARCH records the 9-5/8 cement top at 500 m
    assert result["toc_difference_m"] == 0
    assert any("recorded TOC equals the architecture record" in line for line in cj.summary_lines(result))


# ---- M331: yield-unit registry with exact conversions --------------------------------------------------------
@pytest.mark.parametrize("unit, yield_value, hand_bbl", [
    ("gal/sk", 10.0, 5000 / 42),                         # 500 sk × 10 gal = 5000 gal ÷ 42 gal/bbl = 119.0476 bbl
    ("bbl/sk", 0.2, 100.0),                              # 500 sk × 0.2 bbl
    ("L/sk", 30.0, 94.34716155648157),                   # 15 000 L ÷ 158.987294928 L/bbl
    ("m3/sk", 0.03, 94.34716155648157),                  # 15 m³ ÷ 0.158987294928 m³/bbl
    ("ft3/sk", 1.15, 500 * 1.15 / 5.6146),               # the cement engine constant, unchanged
])
def test_m331_registered_yield_units_convert_exactly(world, unit, yield_value, hand_bbl):
    db, ids, rev = world
    result = cj.reconcile(db, _job(db, ids["dev"], slurry_yield=yield_value), rev["id"], "9-5/8 csg",
                          yield_unit=unit)
    assert result["pumped_bbl"] == pytest.approx(hand_bbl, rel=1e-12)
    assert cj.YIELD_BASIS[unit]


@pytest.mark.parametrize("unit", ["kg/sk", "lb/sk", "ft3", "", "FT3/SK"])
def test_m331_unregistered_or_mass_yield_units_are_refused(world, unit):
    db, ids, rev = world
    with pytest.raises(cj.ReconciliationError):
        cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg", yield_unit=unit)


# ---- M328: replay from immutable snapshots ---------------------------------------------------------------------
def test_m328_cement_replay_uses_the_frozen_job_not_the_edited_report(world):
    db, ids, rev = world
    job_id = _job(db, ids["dev"])
    case = cj.save_case(db, cj.reconcile(db, job_id, rev["id"], "9-5/8 csg", yield_unit="ft3/sk"))
    with db.session_scope() as session:                          # the report is edited after the case was saved
        session.get(CementReport, job_id).cement_volume = 900.0
    outcome = ch.recalculate_entry(_entry(db, case["id"]), db)
    assert outcome["status"] == "MATCH", outcome
    assert outcome["values"]["pumped_bbl"]["value"] == pytest.approx(500 * 1.15 / 5.6146, rel=1e-12)
    assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "NOT_REPRODUCIBLE"   # without the database


def test_m328_a_changed_stored_field_is_different_with_unit_and_tolerance(world):
    db, ids, rev = world
    case = cj.save_case(db, cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg",
                                                   yield_unit="ft3/sk"))
    entry = _entry(db, case["id"])
    results = copy.deepcopy(entry.results)
    results["pumped_bbl"]["value"] += 0.0005                     # inside the 0.001 bbl repeatability tolerance
    assert hr.verify(db, entry.method, entry.inputs, results, entry.version)["status"] == "MATCH"
    results["pumped_bbl"]["value"] += 0.01
    outcome = ch.recalculate_entry(dataclasses.replace(entry, results=results), db)
    assert outcome["status"] == "DIFFERENT"
    (diff,) = outcome["differences"]
    assert diff["field_id"] == "pumped_bbl" and diff["unit"] == "bbl" and diff["tolerance"] == 0.001


def test_m328_pre_snapshot_and_unknown_version_cases_are_not_reproducible(world):
    db, ids, rev = world
    case = cj.save_case(db, cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg",
                                                   yield_unit="ft3/sk"))
    entry = _entry(db, case["id"])
    legacy = {k: v for k, v in entry.inputs.items() if k != "job_snapshot"}
    status = ch.entry_status(dataclasses.replace(entry, inputs=legacy))
    assert status["reproducible"] == "NOT REPRODUCIBLE" and "job_snapshot" in status["reproducible_reason"]
    old = dataclasses.replace(entry, version="M317 v0 (retired)")
    assert ch.recalculate_entry(old, db)["status"] == "NOT_REPRODUCIBLE"


def test_m328_a_tampered_architecture_pin_is_unreadable(world):
    db, ids, rev = world
    case = cj.save_case(db, cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg",
                                                   yield_unit="ft3/sk"))
    entry = _entry(db, case["id"])
    inputs = copy.deepcopy(entry.inputs)
    inputs["components_sha256"]["value"] = "0" * 64
    assert ch.recalculate_entry(dataclasses.replace(entry, inputs=inputs), db)["status"] == "UNREADABLE"
    inputs = copy.deepcopy(entry.inputs)
    del inputs["job_snapshot"]["value"]["sacks"]                   # a malformed snapshot is never "not found"
    assert ch.recalculate_entry(dataclasses.replace(entry, inputs=inputs), db)["status"] == "UNREADABLE"


def test_m328_td_replay_checks_the_frozen_survey_and_string(tmp_path):
    from core import torque_drag_sensitivity as tds
    from core.survey_revisions import stations_sha256
    from core.w13_weight import engine_components
    from test_m318_td_friction_sensitivity import DEVIATED, PIPE

    db = make_file_database(tmp_path / "m328td.db")
    try:
        ids = build_synthetic_operations(db)
        run = {"survey": DEVIATED, "components": engine_components(PIPE), "mud_density_ppg": 10.0, "wob_klbf": 0.0,
               "wellbore_id_in": None,
               "survey_source": {"revision_id": 7, "revision": 2, "stations_sha256": stations_sha256(DEVIATED)}}
        case = tds.save_case(db, tds.sweep(run, [0.1, 0.3]), {"pickup": 200.0}, well_id=ids["dev"])
        entry = _entry(db, case["id"])
        assert entry.inputs["run_snapshot"]["value"]["survey"] == DEVIATED
        assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
        moved = copy.deepcopy(entry.inputs)
        moved["run_snapshot"]["value"]["survey"][2]["inc"] = 46.0
        out = ch.recalculate_entry(dataclasses.replace(entry, inputs=moved), db)
        assert out["status"] == "UNREADABLE" and "survey stations" in out["detail"]
        heavier = copy.deepcopy(entry.inputs)
        heavier["run_snapshot"]["value"]["components"][0]["weight"] = 99.0
        out = ch.recalculate_entry(dataclasses.replace(entry, inputs=heavier), db)
        assert out["status"] == "UNREADABLE" and "components" in out["detail"]
        with pytest.raises(tds.SensitivityError):                    # A-6: an unpinned run is refused
            tds.sweep({**run, "survey_source": {}}, [0.1])
    finally:
        db.engine.dispose()


def test_m328_history_tab_replays_and_stores_a_linked_rerun(world):
    from PySide6.QtWidgets import QApplication

    from tabs.calculation_history_tab import CalculationHistoryTab

    app = QApplication.instance() or QApplication([])
    db, ids, rev = world
    case = cj.save_case(db, cj.reconcile(db, _job(db, ids["dev"]), rev["id"], "9-5/8 csg",
                                                   yield_unit="ft3/sk"))
    tab = CalculationHistoryTab(db)
    try:
        tab.set_well(ids["dev"])
        tab.select_rows([i for i, e in enumerate(tab.entries) if e.key == f"calculation_cases:{case['id']}"])
        assert tab.recalculate()["status"] == "MATCH"
        assert "M328 v1 replay from the frozen snapshot: no field differs" in tab.detail.toPlainText()
        new = tab.save_recalculation()
    finally:
        tab.deleteLater()
        app.processEvents()
    assert new["id"] != case["id"] and new["method"] == cj.METHOD_ID and new["results"] == case["results"]
    link = cc.source_links(db, new["id"])[0]
    assert (link["link_type"], link["source_id"], link["verification_status"]) == ("rerun_of", case["id"], "MATCH")
    assert cc.get_case(db, case["id"])["results"] == case["results"]          # the original is unchanged
