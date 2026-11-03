"""M87: a contract status for every W13 calculator; contract parity with the real W13 handlers;
case save / reopen / re-run / clone / export; legacy ambiguity; dogleg-severity fix.

Goldens are independent closed forms (oilfield relations written out here), offscreen Qt.
"""
from __future__ import annotations

import csv
import io
import math
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

FT = 3.28084


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def w13(app, db):  # noqa: F811
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    tab = EngineeringCalculatorTab(db)
    yield tab
    tab.deleteLater()
    app.processEvents()


def _num(text: str) -> float:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
    return float(match.group(0).replace(",", ""))


def _entry(db, case_id):  # noqa: F811
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


# ---- registry ----------------------------------------------------------------------------------------
def test_every_w13_leaf_calculator_has_a_contract_status(w13):
    from tabs.calculator_finder import build_index

    paths = [e.path for e in build_index(w13.tabs)]
    leaves = [p for p in paths if not any(o != p and o.startswith(p + " › ") for o in paths)]
    assert len(leaves) >= 24
    statuses = {p: contracts.calculator_status(p)[0] for p in leaves}
    assert "UNKNOWN" not in statuses.values(), [p for p, s in statuses.items() if s == "UNKNOWN"]
    assert sum(s == "CONTRACT" for s in statuses.values()) == 18      # 7 at M87; 11 more in M107
    assert set(contracts.CONTRACTS) | set(contracts.NOT_SUPPORTED) == set(leaves)    # nothing stale either


@pytest.mark.parametrize("contract", list(contracts.CONTRACTS.values()), ids=lambda c: c.stable_id)
def test_contract_fields_are_bound_to_live_widgets_with_matching_labels(w13, contract):
    from tabs.calculation_cases_panel import _form_label

    assert contract.structured and contract.method_version.startswith(("M87", "M107")) or \
        contract is contracts.QUICK_CALC
    ids = [spec.field_id for spec in contract.inputs]
    assert len(ids) == len(set(ids))
    for spec in contract.inputs:
        widget = getattr(w13, spec.attr)
        assert widget.objectName() == contracts.OBJECT_PREFIX + spec.attr
        assert _form_label(widget) == spec.label, spec.field_id
        assert spec.unit
    for spec in contract.extras:
        assert hasattr(w13, spec.attr) and callable(getattr(w13, spec.refresh))


# ---- parity with the real handlers + independent goldens --------------------------------------------
def test_quick_calc_parity_and_the_two_length_fields_are_no_longer_confused(w13):
    w13.v_od.setValue(5.0)
    w13.v_id.setValue(4.276)
    w13.v_length.setValue(1000.0)
    w13.v_hole.setValue(8.5)
    w13.v_pipe_od.setValue(5.0)
    w13.v_ann_len.setValue(250.0)
    out = contracts.QUICK_CALC.recalculate({"od": 5.0, "id": 4.276, "length": 1000.0, "hole": 8.5, "pipe_od": 5.0,
                                            "annular_length": 250.0})
    assert out["capacity"] == pytest.approx(4.276 ** 2 / 1029.4 * FT, rel=1e-12)
    assert out["annular_volume"] == pytest.approx((8.5 ** 2 - 5.0 ** 2) / 1029.4 * FT * 250.0, rel=1e-12)
    assert _num(w13.v_cap.text()) == pytest.approx(out["capacity"], abs=5e-6)
    assert _num(w13.v_vol.text()) == pytest.approx(out["volume"], abs=5e-3)
    assert _num(w13.v_ann_vol.text()) == pytest.approx(out["annular_volume"], abs=5e-3)
    assert w13.calculator_finder.open_path("Volume › Quick Calc")
    case = w13.case_bar.save_case("SYN quick v2")
    assert case["method_version"] == "M87 volume quick calc v2"
    bound = {v["field_id"]: v["value"] for v in case["inputs"].values() if v.get("field_id")}
    assert bound["length"] == 1000.0 and bound["annular_length"] == 250.0
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"


def test_legacy_label_bound_case_with_a_repeated_label_is_unreadable(db):  # noqa: F811
    inputs = {"QDoubleSpinBox:1": {"label": "OD", "value": 5.0}, "QDoubleSpinBox:2": {"label": "ID", "value": 4.276},
              "QDoubleSpinBox:3": {"label": "Length", "value": 1000.0},
              "QDoubleSpinBox:6": {"label": "Length", "value": 250.0, "field_id": "length", "unit": "m"}}
    inputs["QDoubleSpinBox:1"].update(field_id="od", unit="in")
    inputs["QDoubleSpinBox:2"].update(field_id="id", unit="in")
    out = contracts.verify_case(contracts.QUICK_CALC_V1.method_id, contracts.QUICK_CALC_V1.method_version, inputs, {})
    assert out["status"] == "UNREADABLE" and "ambiguous label" in out["detail"]
    _i, _r, missing = contracts.annotate(contracts.QUICK_CALC_V1, {k: dict(v) for k, v in inputs.items()}, {})
    assert "length" in missing                                          # never guessed at capture either


def _bit_inputs(w13):
    w13.bit_nozzles = [{"size": 12, "qty": 3}]
    w13._bit_refresh_nozzles()
    for attr, value in (("bit_gpm", 500.0), ("bit_mw", 74.8), ("bit_od", 8.5), ("bit_wob", 25.0), ("bit_rpm", 120.0),
                        ("bit_tq", 8000.0), ("bit_rop", 50.0), ("bit_rig_day", 40000.0), ("bit_trip_h", 6.0),
                        ("bit_rot_h", 20.0), ("bit_cost", 2000.0), ("bit_footage", 500.0)):
        getattr(w13, attr).setValue(value)
    w13._bit_calculate()
    w13._bit_cost_per_foot()


def test_bit_page_parity_with_independent_goldens(w13):
    _bit_inputs(w13)
    values = {"gpm": 500.0, "mw": 74.8, "bit_od": 8.5, "wob": 25.0, "rpm": 120.0, "torque": 8000.0, "rop": 50.0,
              "rig_day": 40000.0, "trip_h": 6.0, "rot_h": 20.0, "bit_cost": 2000.0, "footage": 500.0,
              "nozzles": [{"size": 12, "qty": 3}]}
    out = contracts.BIT_HYDRAULICS.recalculate(values)
    tfa = 3 * math.pi / 4 * (12 / 32) ** 2
    mw_ppg = 74.8 / 7.48052
    assert out["tfa"] == pytest.approx(tfa, rel=1e-12)
    assert out["bit_dp"] == pytest.approx(500 ** 2 * mw_ppg / (10858.0 * tfa ** 2), abs=0.05)   # engine rounds 0.1 psi
    area = math.pi / 4 * 8.5 ** 2
    teale = 25000 / area + 120 * math.pi * 120 * 8000 / (area * 50)          # Teale (1965): WOB/A + 120 pi N T/(A ROP)
    assert out["mse"] == pytest.approx(teale, abs=0.05) and out["mse"] == pytest.approx(127997.67, abs=0.1)
    assert _num(w13.bit_res_dp.text()) == pytest.approx(out["bit_dp"], abs=0.5)
    assert _num(w13.bit_res_hhp.text()) == pytest.approx(out["bit_hhp"], abs=0.05)
    assert _num(w13.bit_res_hsi.text()) == pytest.approx(out["hsi"], abs=0.005)
    assert _num(w13.bit_res_jv.text()) == pytest.approx(out["jet_velocity"], abs=0.5)
    assert _num(w13.bit_res_if.text()) == pytest.approx(out["impact_force"], abs=0.5)
    assert _num(w13.bit_res_mse.text()) == pytest.approx(out["mse"], abs=0.5)
    assert _num(w13.bit_econ_res.text().lstrip("$")) == pytest.approx(out["cost_per_ft"], abs=0.005)
    no_nozzles = contracts.BIT_HYDRAULICS.recalculate({**values, "nozzles": []})
    assert no_nozzles["bit_dp"] is None and no_nozzles["mse"] == pytest.approx(out["mse"])     # never zero


def test_tfa_hydrostatic_owr_cement_parity(w13):
    w13.tfa_gpm.setValue(500.0)
    w13.tfa_mw.setValue(10.0)
    w13.tfa_dp.setValue(1500.0)
    w13._bit_calc_tfa()
    tfa = contracts.TFA.recalculate({"gpm": 500.0, "mw": 10.0, "bit_dp": 1500.0})["tfa"]
    assert tfa == pytest.approx(math.sqrt(10.0 * 500 ** 2 / (10858.0 * 1500.0)), rel=1e-9)
    assert _num(w13.tfa_result.text()) == pytest.approx(tfa, abs=5e-5)

    w13.hp_mw.setValue(74.8)
    w13.hp_tvd.setValue(3000.0)
    w13.hp_sidpp.setValue(350.0)
    w13._wc_calc_hp()
    hp = contracts.HYDROSTATIC.recalculate({"mw": 74.8, "tvd": 3000.0, "sidpp": 350.0})
    assert hp["hydrostatic"] == pytest.approx(0.052 * (74.8 / 7.48) * 3000.0 * FT, abs=0.005)  # engine rounds 0.01
    assert hp["formation_pressure"] == pytest.approx(hp["hydrostatic"] + 350.0, abs=0.01)
    shown = w13.hp_result.toPlainText()
    assert _num(shown.split("Hydrostatic Pressure:")[1]) == pytest.approx(hp["hydrostatic"], abs=0.5)
    assert _num(shown.split("Formation Pressure:")[1]) == pytest.approx(hp["formation_pressure"], abs=0.5)

    w13.mud_oil.setValue(64.0)
    w13.mud_water.setValue(16.0)
    owr = contracts.OWR.recalculate({"oil": 64.0, "water": 16.0})
    assert (owr["oil_ratio"], owr["water_ratio"]) == pytest.approx((80.0, 20.0))

    for attr, value in (("cmt_hole", 12.25), ("cmt_csg", 9.625), ("cmt_len", 3000.0), ("cmt_excess", 50.0),
                        ("cmt_csg_id", 8.681), ("cmt_shoe_track", 60.0)):
        getattr(w13, attr).setValue(value)
    w13._csg_calc_cement()
    values = {s.field_id: getattr(w13, s.attr).value() for s in contracts.CEMENT_VOLUME.inputs}
    cmt = contracts.CEMENT_VOLUME.recalculate(values)
    assert cmt["annular_volume"] == pytest.approx((12.25 ** 2 - 9.625 ** 2) / 1029.4 * 3000.0, rel=1e-3)
    text = w13.cmt_result.toPlainText()
    assert _num(text.split("Annulus:")[1]) == pytest.approx(cmt["annular_volume"], abs=5e-3)
    if cmt["displacement_volume"] is None:
        assert "Displacement: n/a" in text                               # missing is never shown as 0


def test_dogleg_severity_replaces_the_root_sum_square(w13):
    for attr, value in (("dd_init_inc", 30.0), ("dd_final_inc", 30.0), ("dd_init_azi", 0.0), ("dd_final_azi", 90.0),
                        ("dd_interval", 300.0)):
        getattr(w13, attr).setValue(value)
    w13._dd_calc_rates()
    beta = math.degrees(math.acos(math.cos(math.radians(30)) ** 2 + math.sin(math.radians(30)) ** 2 * 0.0))
    expected = beta * 30.0 / 300.0                                      # 4.141 deg/30 m, not sqrt(0 + 9^2) = 9
    out = contracts.BUILD_TURN.recalculate({"inc1": 30.0, "inc2": 30.0, "azi1": 0.0, "azi2": 90.0, "interval": 300.0})
    assert out["dls"] == pytest.approx(expected, rel=1e-9) and out["turn_rate"] == pytest.approx(9.0)
    assert _num(w13.dd_rates.text().split("Dogleg severity:")[1]) == pytest.approx(expected, abs=0.005)
    w13.dd_interval.setValue(0.0)
    w13._dd_calc_rates()
    assert w13.dd_rates.text().startswith("Not assessed")
    with pytest.raises(ValueError):
        contracts.BUILD_TURN.recalculate({"inc1": 0, "inc2": 1, "azi1": 0, "azi2": 0, "interval": 0.0})


# ---- the case lifecycle through the W13 case bar ----------------------------------------------------
def test_bit_case_save_reopen_rerun_clone_export_and_verify(w13, tmp_path, monkeypatch):
    bar = w13.case_bar
    assert w13.calculator_finder.open_path("Bit Hydraulics › Bit Hydraulics")
    _bit_inputs(w13)
    assert "CONTRACT" in bar.contract_label.text()
    case = bar.save_case("SYN bit")
    assert case["method"] == "w13.bit.hydraulics_mse_cost" and case["note"] == ""
    assert case["inputs"]["extra:nozzles"]["value"] == [{"size": 12, "qty": 3}]
    structured = {v["field_id"]: v["value"] for v in case["results"].values() if v.get("source") == "contract"}
    assert structured["bit_dp"] == pytest.approx(500 ** 2 * (74.8 / 7.48052) / (10858.0 * (3 * math.pi / 4 * 0.140625)
                                                                                 ** 2), abs=0.05)
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"

    w13.bit_nozzles = [{"size": 16, "qty": 2}]
    w13._bit_refresh_nozzles()
    w13.bit_gpm.setValue(100.0)
    assert bar.reopen(case["id"]) == []
    assert w13.bit_nozzles == [{"size": 12, "qty": 3}] and w13.bit_gpm.value() == 500.0

    child = bar.rerun(case["id"])
    assert child["parent_id"] == case["id"] and child["method_version"] == case["method_version"]
    assert cc.source_links(w13.db, child["id"])[0]["link_type"] == "rerun_of"

    clone = bar.clone(case["id"], "SYN bit clone")
    assert clone["parent_id"] == case["id"] and clone["inputs"] == case["inputs"]
    assert cc.source_links(w13.db, clone["id"])[0]["link_type"] == "clone_of"
    assert cc.get_case(w13.db, case["id"]) == case                      # the original is untouched

    path = bar.export(case["id"], str(tmp_path / "case.csv"))
    rows = list(csv.reader(io.StringIO(open(path, encoding="utf-8").read())))
    assert ["#", "label", cc.EXPORT_LABEL] in rows
    body = [r for r in rows if r[0] in ("inputs", "results")]
    assert any(r[3] == "bit_dp" and r[4] == "psi" and r[5] == "contract" for r in body)
    assert any(r[3] == "nozzles" and "12" in r[6] for r in body)

    def changed(values):                                                # a silently changed method is caught
        out = contracts._bit_page(values)
        out["bit_dp"] *= 1.01
        return out
    import dataclasses
    patched = dataclasses.replace(contracts.BIT_HYDRAULICS, recalculate=changed)
    monkeypatch.setitem(contracts.CONTRACTS, patched.calculator, patched)
    outcome = contracts.verify_case(case["method"], case["method_version"], case["inputs"], case["results"])
    assert outcome["status"] == "DIFFERENT" and outcome["differences"][0]["field_id"] == "bit_dp"
    monkeypatch.setitem(contracts.AVAILABLE_METHODS, case["method"], ())
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "NOT_REPRODUCIBLE"


def test_not_supported_calculators_say_so_and_store_unversioned(w13):
    bar = w13.case_bar
    assert w13.calculator_finder.open_path("Directional › Anti-Collision")   # Buoyancy has a contract since M107
    assert "NOT_SUPPORTED" in bar.contract_label.text() and "NOT REPRODUCIBLE" in bar.contract_label.text()


def test_invalid_contract_inputs_store_an_unversioned_case_with_the_reason(w13):
    assert w13.calculator_finder.open_path("Bit Hydraulics › TFA Calculator")
    w13.tfa_gpm.setValue(500.0)
    w13.tfa_mw.setValue(10.0)
    w13.tfa_dp.setValue(1500.0)
    w13._bit_calc_tfa()
    w13.tfa_dp.setValue(0.0)                     # inputs changed after the display was produced
    case = w13.case_bar.save_case("SYN tfa invalid")
    assert case["method_version"] == cc.W13_UNVERSIONED and "rejected the inputs" in case["note"]
