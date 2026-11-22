"""M314 (M277): recorded vs recomputed bit hydraulics on a daily report (SYNTHETIC, SCREENING).

Expected values are computed here by hand from the published field formulas, not by calling the engine:
ΔP = Q²·MW/(10858·TFA²), HHP = Q·ΔP/1714, HSI = HHP/(π/4·D²), v = Q/(3.117·TFA), IF = MW·Q·v/1930.
"""
from __future__ import annotations

import json
import math

import pytest

from core import calculation_cases as cc
from core import ddr_hydraulics_check as hc
from core.database import DrillingParameters, MudReport
from synthetic_operations import build_synthetic_operations, make_file_database

NOZZLES = [{"row": 1, "size_32nd": 12, "quantity": 3, "diameter_inch": 0.375, "text": "12/32"}]
TFA = 3 * math.pi / 4 * (12 / 32) ** 2                       # 0.331340 in²
MW_PCF = 74.8052                                            # 10.000 ppg via ÷ 7.48052


def _expected(q, mw_ppg=10.0, tfa=TFA, bit=8.5):
    dp = q * q * mw_ppg / (10858 * tfa * tfa)
    hhp = q * dp / 1714
    return {"dp": dp, "hhp": hhp, "hsi": hhp / (math.pi / 4 * bit * bit), "v": q / (3.117 * tfa),
            "if": mw_ppg * q * (q / (3.117 * tfa)) / 1930}


@pytest.fixture
def world(tmp_path):
    db = make_file_database(tmp_path / "m314.db")
    ids = build_synthetic_operations(db)
    yield db, ids
    db.engine.dispose()


def _record(db, ids, number=1, *, dp=None, muds=(MW_PCF,)):
    from core.database import DailyReport

    report_id = ids["reports"][number]
    with db.session_scope() as session:
        day = session.get(DailyReport, report_id).report_date
    values = {"bit_size": 8.5, "tfa": round(TFA, 4), "nozzles_json": json.dumps(NOZZLES),
              "pump_output_min": 450.0, "pump_output_max": 500.0, "hsi": round(_expected(500)["hsi"], 2)}
    values.update(dp or {})
    with db.session_scope() as session:
        session.add(DrillingParameters(well_id=ids["dev"], report_id=report_id, report_date=day, **values))
        for mw in muds:
            session.add(MudReport(well_id=ids["dev"], report_id=report_id, report_date=day, mw=mw))
    return report_id


def test_recomputes_bit_hydraulics_from_recorded_values(world):
    db, ids = world
    result = hc.check(db, _record(db, ids))
    assert result["status"] == "COMPUTED" and result["tfa_basis"] == "recorded TFA"
    exp = _expected(500, tfa=round(TFA, 4))
    got = result["computed"]["max"]
    assert got["bit_pressure_drop_psi"] == pytest.approx(exp["dp"], abs=0.051)
    assert got["bit_hhp"] == pytest.approx(exp["hhp"], abs=0.006)
    assert got["hsi"] == pytest.approx(exp["hsi"], abs=0.006)
    assert got["jet_velocity_fps"] == pytest.approx(exp["v"], abs=0.051)
    assert got["impact_force_lbs"] == pytest.approx(exp["if"], abs=0.051)
    assert result["computed"]["min"]["flow_gpm"] == 450.0
    assert result["hsi_check"]["status"] == hc.AGREES
    assert result["tfa_check"]["status"] == hc.AGREES
    assert result["inputs"]["mw_ppg"]["value"] == pytest.approx(10.0)
    assert result["inputs"]["mw_pcf"]["source"] == "mud_reports.mw"


def test_a_wrong_recorded_hsi_is_reported_as_different(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"hsi": 20.0}))
    assert result["hsi_check"]["status"] == hc.DIFFERS and "20" in result["hsi_check"]["reason"]


def test_a_recorded_tfa_that_disagrees_with_the_nozzles_is_flagged(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"tfa": 0.5}))
    assert result["tfa_check"]["status"] == hc.DIFFERS and result["tfa_used"] == 0.5


def test_tfa_comes_from_complete_nozzle_rows_only(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"tfa": None}))
    assert result["tfa_basis"] == "TFA from the recorded nozzles"
    assert result["tfa_used"] == pytest.approx(TFA, rel=1e-9)
    open_row = [{"row": 1, "size_32nd": None, "quantity": 3, "text": "Open"}]
    assert hc.tfa_from_nozzles(json.dumps(open_row))["value"] is None
    assert "no explicit size and count" in hc.tfa_from_nozzles(json.dumps(open_row))["reason"]
    no_count = [{"row": 2, "size_32nd": 12, "quantity": None, "text": "12/32"}]
    assert hc.tfa_from_nozzles(no_count)["value"] is None
    assert hc.tfa_from_nozzles("{broken")["reason"] == "nozzle rows are unreadable"


@pytest.mark.parametrize("missing, label", [("bit_size", "bit size"), ("pump_output_min", None)])
def test_missing_inputs_are_named_and_never_zero(world, missing, label):
    db, ids = world
    dp = {missing: None}
    if label is None:                                          # one flow missing still computes the other
        result = hc.check(db, _record(db, ids, dp=dp))
        assert list(result["computed"]) == ["max"] and result["inputs"]["flow_min_gpm"]["status"] == "MISSING"
        return
    result = hc.check(db, _record(db, ids, dp=dp))
    assert result["status"] == "NOT_COMPUTED" and label in result["missing"] and result["computed"] == {}
    assert result["hsi_check"]["status"] == hc.NOT_CHECKED and label in result["hsi_check"]["reason"]


def test_no_tfa_and_no_nozzles_is_not_computed(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"tfa": None, "nozzles_json": None}))
    assert "TFA or nozzles" in result["missing"] and result["tfa_used"] is None


def test_no_mud_weight_and_conflicting_mud_weights_choose_nothing(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, muds=()))
    assert "mud weight" in result["missing"] and result["inputs"]["mw_pcf"]["status"] == "MISSING"
    result = hc.check(db, _record(db, ids, number=2, muds=(70.0, 75.0)))
    assert result["status"] == "NOT_COMPUTED" and result["inputs"]["mw_pcf"]["value"] is None
    assert "2 different mud weights" in result["hsi_check"]["reason"]


def test_no_recorded_hsi_is_not_checked_but_still_computed(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"hsi": None}))
    assert result["status"] == "COMPUTED" and result["hsi_check"]["status"] == hc.NOT_CHECKED


def test_unknown_report_is_refused(world):
    db, _ids = world
    with pytest.raises(LookupError):
        hc.check(db, 987654)


def test_save_stores_an_immutable_case_with_lineage_to_the_source_row(world):
    db, ids = world
    result = hc.check(db, _record(db, ids))
    case = hc.save_check(db, result)
    stored = cc.get_case(db, case["id"])
    assert stored["calculator"] == "DDR hydraulics check" and stored["method_version"] == hc.METHOD_VERSION
    assert stored["results"]["hsi_check"]["value"] == hc.AGREES
    links = cc.source_links(db, case["id"])
    assert links[0]["source_table"] == "drilling_parameters"
    assert links[0]["source_id"] == result["drilling_parameters_id"]
    assert links[0]["verification_status"] == hc.AGREES
    with pytest.raises(ValueError):
        hc.save_check(db, hc.check(db, _record(db, ids, number=2, muds=())))
    # Calculation History lists the case; it never claims a re-run it has no adapter for (stated, not hidden).
    from core import calculation_history as ch
    entry = [e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"]][0]
    status = ch.entry_status(entry)
    assert status["reproducible"] == "REPRODUCIBLE", status       # M328: frozen-snapshot replay adapter
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"


def test_summary_lines_name_scope_and_status(world):
    db, ids = world
    lines = hc.summary_lines(hc.check(db, _record(db, ids, muds=())))
    assert lines[0].startswith("SCREENING") and "Missing: mud weight." in lines


def test_two_drilling_parameter_rows_refuse_to_choose(world):
    db, ids = world
    report_id = _record(db, ids)
    with db.session_scope() as session:
        first = session.query(DrillingParameters).filter_by(report_id=report_id).one()
        session.add(DrillingParameters(well_id=ids["dev"], report_id=report_id, report_date=first.report_date,
                                       bit_size=12.25))
    result = hc.check(db, report_id)
    assert result["status"] == "NOT_COMPUTED" and "2 drilling-parameter records" in result["problems"][0]



# ---- M327: boundaries of the display bands and of the input rules (mutation survivors) ------------------------
def _with_recorded(data, key, value):
    import copy

    out = copy.deepcopy(data)
    out["inputs"][key]["value"] = value
    return hc.evaluate(out)


def test_hsi_band_is_five_percent_on_both_sides_of_the_recomputed_range(world):
    db, ids = world
    data = hc.gather(db, _record(db, ids))
    computed = hc.evaluate(data)["computed"]
    low, high = computed["min"]["hsi"], computed["max"]["hsi"]
    assert low < high
    status = {f: _with_recorded(data, "hsi_recorded", v)["hsi_check"]["status"]
              for f, v in (("above+3%", high * 1.03), ("above+7%", high * 1.07),
                           ("below-3%", low * 0.97), ("below-7%", low * 0.93), ("half", low * 0.5))}
    assert status == {"above+3%": hc.AGREES, "above+7%": hc.DIFFERS, "below-3%": hc.AGREES,
                      "below-7%": hc.DIFFERS, "half": hc.DIFFERS}


def test_tfa_agreement_band_is_one_percent_of_the_nozzle_tfa(world):
    db, ids = world
    data = hc.gather(db, _record(db, ids))
    nozzle = data["inputs"]["tfa_nozzles_in2"]["value"]
    assert _with_recorded(data, "tfa_recorded_in2", nozzle * 1.005)["tfa_check"]["status"] == hc.AGREES
    assert _with_recorded(data, "tfa_recorded_in2", nozzle * 1.05)["tfa_check"]["status"] == hc.DIFFERS
    assert _with_recorded(data, "tfa_recorded_in2", nozzle * 0.95)["tfa_check"]["status"] == hc.DIFFERS


def test_two_drilling_parameter_rows_show_no_values_from_either_row(world):
    db, ids = world
    report_id = _record(db, ids)
    with db.session_scope() as session:
        first = session.query(DrillingParameters).filter_by(report_id=report_id).one()
        session.add(DrillingParameters(well_id=ids["dev"], report_id=report_id, report_date=first.report_date,
                                       bit_size=12.25))
    data = hc.gather(db, report_id)
    assert data["drilling_parameters_id"] is None
    assert all(data["inputs"][k]["value"] is None
               for k in ("bit_size_in", "tfa_recorded_in2", "flow_min_gpm", "flow_max_gpm", "hsi_recorded"))


def test_a_recorded_zero_flow_or_hsi_is_missing_not_a_value(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"pump_output_max": 0.0, "hsi": 0.0}))
    assert list(result["computed"]) == ["min"]
    assert result["inputs"]["flow_max_gpm"]["status"] == "MISSING"
    assert result["inputs"]["hsi_recorded"]["status"] == "MISSING"
    assert result["hsi_check"]["status"] == hc.NOT_CHECKED


def test_evaluate_refuses_to_compute_when_the_snapshot_states_a_problem(world):
    db, ids = world
    data = hc.gather(db, _record(db, ids))
    data["problems"] = ["2 drilling-parameter records on this report; the check needs exactly one"]
    result = hc.evaluate(data)
    assert result["status"] == "NOT_COMPUTED" and result["computed"] == {}
    assert "2 drilling-parameter records" in result["hsi_check"]["reason"]


# ---- UI: the production path (W2 Daily Report -> "💧 Hydraulics check…") ---------------------------------------
def _w2(db, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from core.permissions import permissions
    from tabs.w2_Daily_Report import DailyReportWidget

    permissions.set_user({"id": 1, "username": "m314-synthetic", "role": "engineer"})   # conftest restores
    app = QApplication.instance() or QApplication([])
    errors = []
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda *a, **k: errors.append(a[2] if len(a) > 2 else "") or QMessageBox.Ok)
    return app, DailyReportWidget(db), errors


def test_w2_button_opens_the_check_of_the_open_report_and_saves_a_case(world, monkeypatch):
    from dialogs.ddr_hydraulics_check_dialog import DdrHydraulicsCheckDialog

    db, ids = world
    report_id = _record(db, ids)
    app, tab, _errors = _w2(db, monkeypatch)
    opened = []
    monkeypatch.setattr(DdrHydraulicsCheckDialog, "exec", lambda self: opened.append(self) or 0)
    try:
        assert tab.hydraulics_check_btn.objectName() == "hydraulics_check_btn"
        assert tab.load_report_by_id(report_id) is not False
        tab.hydraulics_check_btn.click()                         # the real signal path
        dialog = opened[0]
        assert dialog.report_id == report_id and dialog.result["status"] == "COMPUTED"
        assert dialog.inputs_table.rowCount() == len(dialog.result["inputs"])
        assert dialog.results_table.columnCount() == 4 and dialog.results_table.item(2, 0).text() == "HSI"
        assert "HSI check: AGREES" in dialog.status.text()
        assert dialog.inputs_table.editTriggers() == dialog.inputs_table.EditTrigger.NoEditTriggers
        assert dialog.save_button.isEnabled()
        dialog.save_button.click()
        assert dialog.saved_case and not dialog.save_button.isEnabled()
        assert cc.get_case(db, dialog.saved_case["id"])["calculator"] == "DDR hydraulics check"
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        del app


def test_w2_missing_inputs_show_dashes_and_cannot_be_saved(world, monkeypatch):
    from dialogs.ddr_hydraulics_check_dialog import DdrHydraulicsCheckDialog

    db, ids = world
    report_id = _record(db, ids, muds=())
    dialog = DdrHydraulicsCheckDialog(db, report_id)
    try:
        assert not dialog.save_button.isEnabled() and dialog.results_table.columnCount() == 2
        mw_row = [r for r in range(dialog.inputs_table.rowCount()) if dialog.inputs_table.item(r, 0).text() == "mw_pcf"]
        assert dialog.inputs_table.item(mw_row[0], 1).text() == "—"           # never "0"
        assert dialog.inputs_table.item(mw_row[0], 3).text() == "MISSING"
        assert "Missing: mud weight." in dialog.status.text()
    finally:
        dialog.deleteLater()


def test_w2_without_a_saved_report_explains_instead_of_opening(world, monkeypatch):
    db, _ids = world
    app, tab, errors = _w2(db, monkeypatch)
    try:
        tab.current_report_id = None
        assert tab.hydraulics_check_dialog() is None
    finally:
        tab.deleteLater()
        del app


def test_no_flow_at_all_names_pump_output_as_missing(world):
    db, ids = world
    result = hc.check(db, _record(db, ids, dp={"pump_output_min": None, "pump_output_max": None}))
    assert result["status"] == "NOT_COMPUTED" and "pump output" in result["missing"]
