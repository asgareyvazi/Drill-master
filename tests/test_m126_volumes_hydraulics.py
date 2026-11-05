"""M126: Well Volumes and Hydraulics are re-runnable W13 contracts.

Well Volumes places the drill string from the surface down to the bit and refuses gaps, overlaps, missing
dimensions and a string that does not reach the bit (D39: the old page overlapped every pipe with every bore
by min(length) and double-counted the annulus). Hydraulics stores the page tables with the case, re-runs the
same engine set-up the page uses and records per-component losses. Goldens are independent closed forms
written out here. Synthetic data only; offscreen Qt.
"""
from __future__ import annotations

import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from core import well_volumes as wv  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

FT = 3.28084
PIPES = [{"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0},
         {"type": "DC", "od": 6.5, "id": 2.8125, "length": 200.0}]
BORES = [{"type": "9 5/8 Casing", "od": 9.625, "id": 8.835, "from": 0.0, "to": 1000.0},
         {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
PUMPS = [{"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0}]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def w13(app, db):  # noqa: F811
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(db)
    yield tab
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _entry(db, case_id):  # noqa: F811
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


def _value(case, field_id):
    return next(v["value"] for v in case["results"].values() if isinstance(v, dict) and v.get("field_id") == field_id)


# ---- Well Volumes: method -----------------------------------------------------------------------------
def test_well_volumes_golden_places_the_string_and_fixes_the_double_count():
    out = wv.assess(PUMPS, PIPES, BORES, 3000.0)
    assert out["status"] == "ASSESSED" and out["reasons"] == []
    string = (4.276 ** 2 * 2800 + 2.8125 ** 2 * 200) / 1029.4 * FT
    annulus = ((8.835 ** 2 - 25.0) * 1000 + (8.5 ** 2 - 25.0) * 1800 + (8.5 ** 2 - 6.5 ** 2) * 200) / 1029.4 * FT
    res = out["results"]
    assert res["string_volume_bbl"] == pytest.approx(string, rel=1e-12)
    assert res["annular_volume_bbl"] == pytest.approx(annulus, rel=1e-12)
    assert res["circulating_volume_bbl"] == pytest.approx(string + annulus, rel=1e-12)
    assert res["flow_rate_gpm"] == pytest.approx(420.0)
    assert res["lag_time_min"] == pytest.approx(annulus / 10.0)          # 420 gpm = 10 bbl/min
    assert res["surface_to_bit_min"] == pytest.approx(string / 10.0)
    assert res["bottoms_up_strokes"] == pytest.approx(annulus / 0.1)
    # The pre-M126 page overlapped each pipe with each bore by min(lengths): 3400 m of annulus in a 3000 m well.
    old = ((8.835 ** 2 - 25.0) * 1000 + (8.5 ** 2 - 25.0) * 2000 + (8.835 ** 2 - 6.5 ** 2) * 200
           + (8.5 ** 2 - 6.5 ** 2) * 200) / 1029.4 * FT
    assert old - res["annular_volume_bbl"] > 50.0
    placed = [(r["name"], r["top_m"], r["bottom_m"]) for r in out["components"] if r["kind"] == "annulus"]
    assert placed == [("DP (row 1) in 9 5/8 Casing", 0.0, 1000.0), ("DP (row 1) in Open Hole", 1000.0, 2800.0),
                      ("DC (row 2) in Open Hole", 2800.0, 3000.0)]


@pytest.mark.parametrize("change, reason", [
    (dict(sections=BORES[:1]), "no casing / open-hole row covers 1000.00-3000.00 m"),
    (dict(sections=[BORES[0], dict(BORES[1], **{"from": 900.0})]), "overlap"),
    (dict(string=PIPES[:1]), "add up to 2800.00 m but the bit depth is 3000.00 m"),
    (dict(string=[dict(PIPES[0], id=0)] + PIPES[1:]), "string row 1: OD, ID and length must be entered"),
    (dict(sections=[dict(BORES[0], id=4.9), BORES[1]]), "is not smaller than the bore ID"),
    (dict(bit=0.0), "bit depth is missing"),
    (dict(pumps=[{"name": "x", "output_bbl_stk": 0.0, "spm": 90}]), "needs a positive output"),
])
def test_well_volumes_refuses_what_it_cannot_place(change, reason):
    out = wv.assess(change.get("pumps", PUMPS), change.get("string", PIPES), change.get("sections", BORES),
                    change.get("bit", 3000.0))
    assert out["status"] == "NOT ASSESSED" and any(reason in r for r in out["reasons"]), out["reasons"]
    assert all(v is None for v in out["results"].values()) and out["components"] == []


def test_no_running_pump_leaves_times_unknown_and_unequal_spm_has_no_single_stroke_count():
    idle = wv.assess([dict(PUMPS[0], spm=0.0)], PIPES, BORES, 3000.0)
    assert idle["status"] == "ASSESSED" and idle["results"]["annular_volume_bbl"] > 0
    assert idle["results"]["lag_time_min"] is None and idle["results"]["flow_rate_gpm"] is None
    two = wv.assess(PUMPS + [{"name": "SYN P2", "output_bbl_stk": 0.1, "spm": 80.0}], PIPES, BORES, 3000.0)
    assert two["results"]["flow_rate_gpm"] == pytest.approx(756.0) and two["results"]["bottoms_up_strokes"] is None
    assert any("different SPM" in n for n in two["notes"])


# ---- Well Volumes: the real page and its cases -------------------------------------------------------
def _fill_volumes(w13):
    assert w13.calculator_finder.open_path("Volume › Well Volumes")
    w13.vol_pumps[:], w13.vol_pipes[:], w13.vol_casings[:] = [dict(p) for p in PUMPS], \
        [dict(p) for p in PIPES], [dict(b) for b in BORES]
    w13._vol_refresh_pump_table()
    w13._vol_refresh_pipe_table()
    w13._vol_refresh_csg_table()
    w13.vol_depth.setValue(3000.0)
    w13._vol_calculate()


def test_well_volumes_page_case_saves_reruns_reopens_and_detects_a_changed_row(w13):
    _fill_volumes(w13)
    assert "Circulating volume" in w13.vol_results.toPlainText()
    w13.case_bar.refresh()
    assert "Class: CONTRACT" in w13.case_bar.contract_label.text()
    case = w13.case_bar.save_case("SYN volumes")
    assert case["method_version"] == "M126 well volumes v1"
    assert _value(case, "annular_volume_bbl") == pytest.approx(w13.vol_assessment["results"]["annular_volume_bbl"])
    assert len(_value(case, "components")) == 1 + 2 + 3
    entry = _entry(w13.db, case["id"])
    assert entry.scope == "W13 CALCULATOR — CONTRACT" and ch.recalculate_entry(entry)["status"] == "MATCH"
    # reopen restores the tables into a cleared page
    w13.vol_pipes.clear()
    w13._vol_refresh_pipe_table()
    assert w13.case_bar.reopen(case["id"]) == []
    assert w13.vol_pipes == PIPES and w13.vol_pipe_table.rowCount() == 2
    # a changed stored row is DIFFERENT (totals and component rows)
    changed = {k: dict(v) for k, v in case["inputs"].items()}
    changed["extra:pipes"]["value"] = [dict(PIPES[0], length=2700.0), dict(PIPES[1], length=300.0)]
    outcome = contracts.verify_case(case["method"], case["method_version"], changed, case["results"])
    assert outcome["status"] == "DIFFERENT"
    assert {d["field_id"] for d in outcome["differences"]} >= {"string_volume_bbl", "components"}
    rows = [dict(r) for r in _value(case, "components")]
    rows[-1]["volume_bbl"] += 0.01
    tampered = {k: (dict(v, value=rows) if v.get("field_id") == "components" else v) for k, v in case["results"].items()}
    outcome = contracts.verify_case(case["method"], case["method_version"], case["inputs"], tampered)
    assert [d["field_id"] for d in outcome["differences"]] == ["components"]


def test_a_not_assessed_well_volume_page_is_saved_unversioned_with_the_reason(w13):
    _fill_volumes(w13)
    w13.vol_casings[:] = [dict(BORES[0])]
    w13._vol_refresh_csg_table()
    w13._vol_calculate()
    assert w13.vol_results.toPlainText().startswith("NOT ASSESSED")
    case = w13.case_bar.save_case("SYN volumes gap")
    assert case["method_version"] != "M126 well volumes v1" and "no casing / open-hole row covers" in case["note"]


# ---- Hydraulics ---------------------------------------------------------------------------------------
def _fill_hydraulics(w13, spm=100.0):
    assert w13.calculator_finder.open_path("Hydraulics")
    w13.hy_pumps[:] = [dict(PUMPS[0], spm=spm)]
    w13._hy_refresh_pump_table()
    w13.hy_pipe_rows = [dict(p, weight=19.5) for p in PIPES]
    w13.hy_csg_rows = BORES
    w13.hy_nzl_rows = [{"size": 12, "qty": 3}]
    w13._hy_update_tfa()
    w13.hy_bit_diameter.setValue(8.5)
    w13.hy_model.setCurrentText("Bingham Plastic")
    w13.hy_wt.setCurrentText("Vertical")
    w13.hy_bit_dep.setValue(3000.0)
    w13.hy_confirm_defaults.setChecked(True)
    w13._hy_run_calc()
    return w13.hy_result


def test_hydraulics_page_matches_independent_closed_forms(w13):
    r = _fill_hydraulics(w13)
    assert not r.errors and r.scope == "SCREENING"
    mw_ppg, q = 90.0 / 7.48052, 420.0
    tfa = 3 * math.pi / 4 * (12 / 32) ** 2
    bit_dp = q ** 2 * mw_ppg / (10858.0 * tfa ** 2)
    assert r.tfa_in2 == pytest.approx(tfa, abs=1e-4) and r.bit_loss_psi == pytest.approx(bit_dp, rel=1e-3)
    assert r.bit_hhp == pytest.approx(r.bit_loss_psi * q / 1714.0, rel=1e-3)
    assert r.hsi == pytest.approx(r.bit_hhp / (math.pi / 4 * 8.5 ** 2), rel=1e-2)
    out = contracts.CONTRACTS["Hydraulics"].recalculate(w13._hy_values())
    parts = out["surface_loss_psi"] + out["string_loss_psi"] + out["annular_loss_psi"] + out["bit_loss_psi"]
    assert out["total_loss_psi"] == pytest.approx(parts, abs=0.1)           # rows are rounded to 0.01 psi
    assert out["ecd_at_bit_ppg"] == pytest.approx(mw_ppg + out["annular_loss_psi"] / (0.052 * 3000 * FT), abs=2e-3)
    # independent Bingham annulus rows for DP in the open hole (v = Q / 2.448 (Dh^2 - Dp^2) ft/s; gap 3.5 in):
    # 420 gpm is turbulent - MW^0.75 v^1.75 PV^0.25 L / (1396 gap^1.25) ...
    gap, length = 8.5 - 5.0, 1800.0 * FT
    dp_oh = _dp_open_hole_row(w13)
    v = q / (2.448 * (8.5 ** 2 - 5.0 ** 2))
    assert dp_oh["regime"] == "Turbulent"
    assert dp_oh["loss_psi"] == pytest.approx(mw_ppg ** 0.75 * v ** 1.75 * 15.0 ** 0.25 * length / (1396 * gap ** 1.25),
                                              rel=2e-3)
    # ... and 30 SPM (126 gpm) is laminar - PV v L / (1000 gap^2) + YP L / (200 gap)
    _fill_hydraulics(w13, spm=30.0)
    dp_oh = _dp_open_hole_row(w13)
    v = 126.0 / (2.448 * (8.5 ** 2 - 5.0 ** 2))
    assert dp_oh["regime"] == "Laminar"
    assert dp_oh["loss_psi"] == pytest.approx(15.0 * v * length / (1000 * gap ** 2) + 11.0 * length / (200 * gap),
                                              rel=2e-3)


def test_component_rows_carry_their_own_velocity(w13):
    """Pipe v = Q / (2.448 ID^2), annulus v = Q / (2.448 (Dh^2 - OD^2)) ft/s, x60 ft/min, each on its own row."""
    _fill_hydraulics(w13)
    ids = {"DP": 4.276, "DC": 2.8125}
    ods = {"DP": 5.0, "DC": 6.5}
    holes = {"Casing": 8.835, "Open Hole": 8.5}
    rows = contracts.CONTRACTS["Hydraulics"].components(w13._hy_values())
    for row in rows:
        if row["kind"] == "pipe":
            expected = 420.0 / (2.448 * ids[row["name"][:2]] ** 2) * 60
        elif row["kind"] == "annulus":
            hole = holes["Open Hole" if row["name"].endswith("Open Hole") else "Casing"]
            expected = 420.0 / (2.448 * (hole ** 2 - ods[row["name"][:2]] ** 2)) * 60
        else:
            continue
        assert row["velocity_ft_min"] == pytest.approx(expected, abs=0.1), row["name"]


def test_a_not_recorded_bit_diameter_runs_without_hsi_and_reruns(w13):
    _fill_hydraulics(w13)
    w13.hy_bit_diameter.setValue(w13.hy_bit_diameter.minimum())        # "Not recorded"
    w13._hy_run_calc()
    assert w13.hy_result is not None and not w13.hy_result.errors and w13.hy_result.hsi is None
    case = w13.case_bar.save_case("SYN hydraulics no bit size")
    assert case["method_version"].startswith("M126") and _value(case, "hsi") is None
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"


def _dp_open_hole_row(w13):
    rows = contracts.CONTRACTS["Hydraulics"].components(w13._hy_values())
    return next(row for row in rows if row["kind"] == "annulus" and row["name"].startswith("DP")
                and row["name"].endswith("vs Open Hole"))


def test_hydraulics_case_saves_component_rows_reruns_and_reopens(w13):
    r = _fill_hydraulics(w13)
    case = w13.case_bar.save_case("SYN hydraulics")
    assert case["method_version"] == "M126 circulating-system hydraulics v1"
    assert _value(case, "total_loss_psi") == pytest.approx(r.total_loss_psi)
    assert _value(case, "ecd_at_bit_ppg") == pytest.approx(r.ecd_at_bit_ppg)
    kinds = [row["kind"] for row in _value(case, "components")]
    assert kinds[0] == "surface" and kinds[-1] == "bit" and kinds.count("pipe") == kinds.count("annulus") == 3
    entry = _entry(w13.db, case["id"])
    assert entry.scope == "W13 CALCULATOR — SCREENING CONTRACT" and ch.recalculate_entry(entry)["status"] == "MATCH"
    w13.hy_pipe_rows, w13.hy_nzl_rows = [], []
    assert w13.case_bar.reopen(case["id"]) == []
    assert [row["length"] for row in w13.hy_pipe_rows] == [2800.0, 200.0] and w13.hy_nzl_rows == [{"size": 12, "qty": 3}]
    assert w13.hy_result is None                                    # restored inputs invalidate old results
    changed = {k: dict(v) for k, v in case["inputs"].items()}
    changed["extra:pumps"]["value"] = [dict(PUMPS[0], spm=110.0)]
    outcome = contracts.verify_case(case["method"], case["method_version"], changed, case["results"])
    assert outcome["status"] == "DIFFERENT" and "components" in {d["field_id"] for d in outcome["differences"]}


@pytest.mark.parametrize("setup, reason", [
    ("unconfirmed", "not confirmed"), ("directional", "directional measured survey TVD"),
    ("hb", "Herschel-Bulkley"), ("no_pump", "positive pump flow rate"),
])
def test_hydraulics_refusals_are_not_saved_as_reproducible(w13, setup, reason):
    _fill_hydraulics(w13, spm=0.0 if setup == "no_pump" else 100.0)
    if setup == "unconfirmed":
        w13.hy_confirm_defaults.setChecked(False)
    elif setup == "directional":
        w13.hy_wt.setCurrentText("Directional")
    elif setup == "hb":
        w13.hy_model.setCurrentText("Herschel-Bulkley (unsupported)")
    with pytest.raises(ValueError, match=reason):
        contracts.CONTRACTS["Hydraulics"].recalculate(w13._hy_values())
    if setup != "unconfirmed":
        w13._hy_run_calc()
        assert w13.hy_result is None or w13.hy_result.errors       # the page refuses too: no ECD, no numbers


def test_the_page_and_the_contract_configure_the_engine_identically(w13):
    _fill_hydraulics(w13)
    from core import w13_hydraulics
    page = w13.hy_result
    contract = w13_hydraulics.run(dict(w13._hy_values(), bit_diameter=8.5))
    assert w13_hydraulics.scalar_results(page) == w13_hydraulics.scalar_results(contract)
    assert w13_hydraulics.component_rows(page) == w13_hydraulics.component_rows(contract)
