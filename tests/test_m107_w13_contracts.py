"""M107: a contract or an exact NOT_SUPPORTED reason for every W13 leaf calculator.

Parity: each new adapter against the real W13 handler on screen. Goldens are independent closed forms
written out here (oilfield relations), not the engines. D26: the weight-up sack count (additive density was
missing from the sack mass; barite was listed as "1470 pcf"). Offscreen Qt.
"""
from __future__ import annotations

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
BBL_FT3 = 42.0 / 7.4805
NEW = ("CSG/CMT › Buoyancy", "CSG/CMT › Balanced Plug", "Well Control › Kick Tolerance",
       "Well Control › Pore Press  FG", "Stuck Pipe", "Mud › Weight/Dilution/Mix", "Mud › Volume Balance",
       "Mud › Mud Lab", "Fishing", "Mud › Rheology", "Bit Hydraulics › Nozzle Optimization")


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


def _after(text: str, marker: str) -> float:
    return _num(text.split(marker, 1)[1])


def _set(w13, **values):
    for attr, value in values.items():
        widget = getattr(w13, attr)
        if isinstance(widget, QtWidgets.QComboBox):
            widget.setCurrentText(value)
        elif isinstance(widget, QtWidgets.QAbstractButton):
            widget.setChecked(bool(value))
        else:
            widget.setValue(value)


def _values(w13, contract):
    from tabs.calculation_cases_panel import _read

    return contracts.input_values(contract, {
        spec.attr: {"field_id": spec.field_id, "value": _read(getattr(w13, spec.attr))} for spec in contract.inputs})


def _entry(db, case_id):  # noqa: F811
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


# ---- registry ----------------------------------------------------------------------------------------
def test_all_27_leaves_have_a_contract_or_an_exact_reason(w13):
    from tabs.calculator_finder import build_index

    paths = [e.path for e in build_index(w13.tabs)]
    leaves = [p for p in paths if not any(o != p and o.startswith(p + " › ") for o in paths)]
    assert len(leaves) == 27 and set(contracts.CONTRACTS) | set(contracts.NOT_SUPPORTED) == set(leaves)
    assert not set(contracts.CONTRACTS) & set(contracts.NOT_SUPPORTED)
    assert len(contracts.CONTRACTS) == 23 and len(contracts.NOT_SUPPORTED) == 4   # M126 +2; M127 +2; M128 Choke
    assert set(NEW) <= set(contracts.CONTRACTS)
    for calculator, reason in contracts.NOT_SUPPORTED.items():
        assert "not yet contracted" not in reason and len(reason) > 40, calculator
    ids = [c.stable_id for c in contracts.CONTRACTS.values()]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"w13(\.[a-z_]+){2}", i) for i in ids)
    for calculator in NEW:
        contract = contracts.CONTRACTS[calculator]
        assert contract.structured and contract.method_version.startswith("M107") and contract.reference
        assert len({s.field_id for s in contract.results}) == len(contract.results)


def test_exact_reasons_name_what_is_not_captured():
    reasons = contracts.NOT_SUPPORTED
    assert "Volume › Well Volumes" not in reasons and "Hydraulics" not in reasons   # contracted in M126
    assert "Weight" not in reasons and "CSG/CMT › Casing Strength" not in reasons   # contracted in M127
    assert "TRAINING AID" in reasons["Well Control › Kill Sheet"]
    assert "Well Control › Choke Schedule" not in reasons     # M128: a WORKSHEET contract (schedule rows)
    assert "not a calculator" in reasons["DP Database"]


def test_nested_radio_buttons_take_their_form_row_label(w13):
    from tabs.calculation_cases_panel import _form_label

    assert _form_label(w13.opt_hp_model) == "Model" and _form_label(w13.opt_if_model) == "Model"


# ---- parity + independent goldens --------------------------------------------------------------------
def test_buoyancy_parity_and_not_recorded_is_never_zero(w13):
    _set(w13, bf_mw=74.8, bf_csg_wt=40.0, bf_csg_len=5000.0, bf_friction=0.2)
    w13._csg_calc_landing()
    out = contracts.BUOYANCY.recalculate(_values(w13, contracts.BUOYANCY))
    bf = round(1.0 - 74.8 / 490.0, 4)
    assert out["buoyancy_factor"] == bf
    assert out["hook_load"] == pytest.approx(40.0 * 5000.0 * bf * (1.0 - 0.2), rel=1e-9)
    text = w13.bf_result.text()
    assert _after(text, "Buoyancy Factor:") == pytest.approx(bf) and _after(text, "Hook Load:") == \
        pytest.approx(out["hook_load"], abs=0.5)
    w13.bf_friction.setValue(-1.0)                       # "Not recorded"
    partial = contracts.BUOYANCY.recalculate(_values(w13, contracts.BUOYANCY))
    assert partial["buoyancy_factor"] == bf
    w13.bf_mw.setValue(-1.0)
    with pytest.raises(ValueError, match="not recorded"):
        contracts.BUOYANCY.recalculate(_values(w13, contracts.BUOYANCY))


def test_balanced_plug_parity(w13):
    w13._plug_calculate()
    out = contracts.BALANCED_PLUG.recalculate(_values(w13, contracts.BALANCED_PLUG))
    text = w13.plug_result.toPlainText()
    assert _after(text, "Slurry volume") == pytest.approx(out["slurry_volume"], abs=5e-4)
    assert _after(text, "Displacement") == pytest.approx(out["displacement"], abs=5e-4)
    assert _after(text, "Top of cement, pipe in") == pytest.approx(out["top_pipe_in"], abs=5e-3)
    assert out["sacks"] is None and "n/a (no yield entered)" in text            # no yield: never a number
    hole_cap = 8.75 ** 2 / 1029.4
    assert out["slurry_volume"] == pytest.approx(hole_cap * 500.0 * 1.2, rel=1e-3)


def test_kick_tolerance_and_trip_margin_parity(w13):
    w13._wc_calc_kt()
    w13._wc_calc_trip_margin()
    out = contracts.KICK_TOLERANCE.recalculate(_values(w13, contracts.KICK_TOLERANCE))
    assert out["maasp"] == pytest.approx((13.5 - 10.0) * 0.052 * 8000.0, abs=0.5)
    assert out["trip_margin"] == pytest.approx(0.5) and out["trip_margin_psi"] == pytest.approx(0.5 * 0.052 * 10000.0)
    assert _after(w13.kt_result.text(), "MAASP:") == pytest.approx(out["maasp"], abs=0.5)
    assert _after(w13.kt_result.text(), "Kick tolerance:") == pytest.approx(out["kick_tolerance"], abs=0.01)
    assert _after(w13.tm_result.text(), "Trip margin:") == pytest.approx(out["trip_margin"], abs=5e-4)


def test_pore_fg_parity(w13):
    w13._wc_calc_eaton()
    w13._wc_calc_influx_type()
    w13._wc_calc_d_exp()
    out = contracts.PORE_FG.recalculate(_values(w13, contracts.PORE_FG))
    nu, obg, pp = 0.25, 0.95, 0.52
    assert out["fracture_gradient"] == pytest.approx(nu / (1 - nu) * (obg - pp) + pp, abs=1e-5)
    assert out["influx_height"] == pytest.approx(10.0 / 0.0459, abs=0.01)
    d = math.log10(30.0 / (60.0 * 80.0)) / math.log10(12.0 * 25000.0 / (1e6 * 8.5))
    assert out["d_exponent"] == pytest.approx(d, abs=1e-4) and out["dc_exponent"] == pytest.approx(d * 8.6 / 12.0,
                                                                                                    abs=1e-4)
    assert _num(w13.pp_eaton_res.text()) == pytest.approx(out["fracture_gradient"], abs=5e-5)
    assert _after(w13.pp_d_res.text(), "dc =") == pytest.approx(out["dc_exponent"], abs=5e-5)


def test_stuck_pipe_parity_and_unrecorded_inputs(w13):
    with pytest.raises(ValueError):                    # every input untouched = "Not recorded"
        contracts.STUCK_PIPE.recalculate(_values(w13, contracts.STUCK_PIPE))
    _set(w13, stk_stretch_in=20.0, stk_wt=19.5, stk_pull=50000.0, stk_pipe_od=5.0, stk_pipe_id=4.276)
    w13._update_stuck()
    out = contracts.STUCK_PIPE.recalculate(_values(w13, contracts.STUCK_PIPE))
    assert out["free_point"] == pytest.approx(735294.0 * 20.0 * 19.5 / 50000.0, abs=0.05)
    assert out["adjusted_weight"] == pytest.approx((5.0 ** 2 - 4.276 ** 2) * 2.67, abs=0.005)
    assert out["string_stretch"] is None                # length and MW not recorded
    assert _num(w13.stk_free_point.text().split("≈")[1]) == pytest.approx(out["free_point"], abs=0.05)
    assert "NOT ASSESSED" in w13.stk_stretch.text()


def test_weight_up_d26_dilution_mix_parity(w13):
    assert [w13.mud_wu_additive.itemText(i) for i in range(w13.mud_wu_additive.count())] == \
        [name for name, _ in contracts.WEIGHT_UP_ADDITIVES]
    _set(w13, mud_wu_cur=80.0, mud_wu_tar=90.0, mud_wu_vol=500.0, mud_wu_additive="Barite (4.20 SG, 262.2 pcf)",
         mud_dil_cur=90.0, mud_dil_tar=80.0, mud_dil_vol=500.0, mud_dilant_mw=62.4)
    w13._mud_wu()
    w13._mud_dil()
    w13._mud_mix()
    out = contracts.MUD_WDM.recalculate(_values(w13, contracts.MUD_WDM))
    barite_bbl = 500.0 * (90.0 - 80.0) / (262.2 - 90.0)                 # volume balance
    sacks = barite_bbl * BBL_FT3 * 262.2 / 100.0                        # mass (lb) / 100-lb sacks
    assert sacks == pytest.approx(427.4, abs=0.1)                       # was 1.52 before D26
    assert out["sacks"] == pytest.approx(sacks, abs=0.005)
    assert out["volume_increase"] == pytest.approx(barite_bbl, abs=5e-4)
    assert out["water_required"] == pytest.approx(500.0 * 10.0 / (80.0 - 62.4), abs=5e-4)
    assert out["mix_mw"] == pytest.approx((80 * 300 + 100 * 200) / 500.0)
    assert _after(w13.mud_wu_res.text(), "Additive:") == pytest.approx(sacks, abs=0.5)
    assert _after(w13.mud_dil_res.text(), "Water Required:") == pytest.approx(out["water_required"], abs=0.05)
    assert _after(w13.mud_mix_res.text(), "Final MW:") == pytest.approx(88.0, abs=0.05)
    assert contracts.additive_density_pcf("Barite (1470 pcf)") is None   # the old entry is not a density
    from core.engineering.engines.mud_volume import MudVolumeEngine

    assert "v2" in MudVolumeEngine.weight_up(80.0, 90.0, 500.0, 262.2).method


def test_weight_up_reference_table_shows_the_corrected_formula():
    import inspect

    from tabs import w15_Reference_Tables

    source = inspect.getsource(w15_Reference_Tables)
    assert "(1470 - TargetMW)" not in source and "ρ_add" in source


def test_volume_balance_mud_lab_fishing_rheology_parity(w13):
    _set(w13, mud_bal_add=10.0, mud_bal_loss=5.0)
    w13._mud_balance()
    bal = contracts.MUD_BALANCE.recalculate(_values(w13, contracts.MUD_BALANCE))
    assert bal == {"final_volume": 805.0, "net_change": 5.0}
    assert _after(w13.mud_bal_res.toPlainText(), "Final volume:") == pytest.approx(805.0)

    for handler in (w13._mud_lab, w13._mud_lab_lsryp, w13._mud_lab_lime, w13._mud_lab_corrosion, w13._mud_lab_slug):
        handler()
    lab = contracts.MUD_LAB.recalculate(_values(w13, contracts.MUD_LAB))
    assert lab["mbt"] == pytest.approx(5 * 5.0 / 2.0) and lab["lsryp"] == pytest.approx(2 * 6.0 - 4.0)
    assert lab["corrosion_mpy"] == pytest.approx(534 * 100.0 / (3.0 * 168.0 * 7.86), abs=0.005)
    assert lab["dry_pipe_length"] == pytest.approx(20 * (12.5 - 10.0) / (0.01776 * 10.0), abs=0.05)
    assert _num(w13.ml_cr_res.text()) == pytest.approx(lab["corrosion_mpy"], abs=0.005)

    w13._calc_fish_sizing()
    w13._calc_jar_range()
    fish = contracts.FISHING.recalculate(_values(w13, contracts.FISHING))
    assert fish["clearance"] == pytest.approx(0.3) and fish["compatible"] == 1.0
    assert fish["jar_setting"] == pytest.approx(_after(w13.jar_result.text(), "Recommended Jar ="), abs=0.5)
    assert fish["buoyant_weight"] == pytest.approx(200000 * 0.85) and fish["backoff_depth"] is None
    _set(w13, fish_os_id=4.0)
    assert contracts.FISHING.recalculate(_values(w13, contracts.FISHING))["compatible"] == 0.0

    _set(w13, rh_t600=60.0, rh_t300=40.0, rh_t6=7.0, rh_t3=5.0)
    w13._mud_rheo()
    rh = contracts.RHEOLOGY.recalculate(_values(w13, contracts.RHEOLOGY))
    assert (rh["pv"], rh["yp"], rh["tau_y"]) == (20.0, 20.0, 3.0)
    assert rh["n"] == pytest.approx(3.32 * math.log10(60 / 40), abs=1e-9)
    assert _after(w13.rh_result.toPlainText(), "PV:") == pytest.approx(rh["pv"])


def test_nozzle_optimisation_parity_and_zero_fallbacks_are_rejected(w13):
    w13._bit_optimize()
    out = contracts.NOZZLE_OPTIMIZATION.recalculate(_values(w13, contracts.NOZZLE_OPTIMIZATION))
    text = w13.opt_results.toPlainText()
    assert out["max_flow_rate"] == pytest.approx(round(1000 * 1714.0 / 3500.0, 1))
    assert _after(text, "Optimal Flow Rate:") == pytest.approx(out["optimal_flow_rate"])
    assert _after(text, "Actual TFA:") == pytest.approx(out["actual_tfa"])
    sizes = [int(s) for s in re.findall(r"(\d+)/32", text)]
    assert sizes == [int(out[f"nozzle_{i}"]) for i in range(1, len(sizes) + 1)] and out["nozzle_4"] is None
    assert out["friction_exponent_assumed"] == 0.0
    _set(w13, opt_hp_model=False, opt_if_model=True)
    impact = contracts.NOZZLE_OPTIMIZATION.recalculate(_values(w13, contracts.NOZZLE_OPTIMIZATION))
    assert impact["optimal_flow_rate"] != out["optimal_flow_rate"]          # the model choice is an input
    _set(w13, opt_max_press=0.0)
    with pytest.raises(ValueError):
        contracts.NOZZLE_OPTIMIZATION.recalculate(_values(w13, contracts.NOZZLE_OPTIMIZATION))


# ---- persistence: save / reopen / re-run, text and bool inputs ---------------------------------------
def test_text_input_case_saves_reruns_and_detects_a_changed_additive(w13):
    assert w13.calculator_finder.open_path("Mud › Weight/Dilution/Mix")
    _set(w13, mud_dilant_mw=62.4)
    w13._mud_wu()
    w13._mud_dil()
    w13._mud_mix()
    case = w13.case_bar.save_case("SYN wdm")
    assert case["method_version"] == contracts.MUD_WDM.method_version
    bound = {v["field_id"]: v["value"] for v in case["inputs"].values() if v.get("field_id")}
    assert bound["additive"] == "Barite (4.20 SG, 262.2 pcf)"
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"
    changed = {k: dict(v) for k, v in case["inputs"].items()}
    key = next(k for k, v in changed.items() if v.get("field_id") == "additive")
    changed[key]["value"] = "Hematite (320 pcf)"
    outcome = contracts.verify_case(case["method"], case["method_version"], changed, case["results"])
    assert outcome["status"] == "DIFFERENT" and {d["field_id"] for d in outcome["differences"]} >= {"sacks"}
    changed[key]["value"] = ""
    assert contracts.verify_case(case["method"], case["method_version"], changed, case["results"])["status"] == \
        "UNREADABLE"


def test_bool_input_case_saves_and_reruns(w13):
    assert w13.calculator_finder.open_path("Bit Hydraulics › Nozzle Optimization")
    _set(w13, opt_hp_model=False, opt_if_model=True)
    w13._bit_optimize()
    case = w13.case_bar.save_case("SYN nozzles IF")
    bound = {v["field_id"]: v["value"] for v in case["inputs"].values() if v.get("field_id")}
    assert bound["model_hp"] is False
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"


@pytest.mark.parametrize("calculator", ["CSG/CMT › Buoyancy", "Stuck Pipe", "Well Control › Kick Tolerance"])
def test_new_contract_cases_record_the_method_and_rerun(w13, calculator):
    assert w13.calculator_finder.open_path(calculator)
    if calculator == "CSG/CMT › Buoyancy":
        _set(w13, bf_mw=74.8, bf_csg_wt=40.0, bf_csg_len=5000.0, bf_friction=0.2)
        w13._csg_calc_landing()
    elif calculator == "Stuck Pipe":
        _set(w13, stk_stretch_in=20.0, stk_wt=19.5, stk_pull=50000.0)
        w13._update_stuck()
    else:
        w13._wc_calc_kt()
        w13._wc_calc_trip_margin()
    case = w13.case_bar.save_case(f"SYN {calculator}")
    assert case["method_version"] == contracts.CONTRACTS[calculator].method_version != cc.W13_UNVERSIONED
    assert ch.recalculate_entry(_entry(w13.db, case["id"]))["status"] == "MATCH"


def test_hydraulics_runs_are_contract_cases_not_a_hydraulics_table():
    """M87 claimed saved hydraulics runs in a table that never existed. Since M126 a Hydraulics run is stored
    as a W13 contract case (calculation_cases) and re-run from there - still no hydraulics table is implied."""
    from core import calculator_contracts as cc
    from core.database import Base

    assert "Hydraulics" not in cc.NOT_SUPPORTED
    assert cc.CONTRACTS["Hydraulics"].method_version.startswith("M126")
    assert not any("hydraulic" in m.class_.__tablename__ for m in Base.registry.mappers)
