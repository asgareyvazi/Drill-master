"""M128: the W13 "Choke Schedule" page is a WORKSHEET contract of the drill-pipe pressure schedule (D43).

The page was titled "Choke Pressure Schedule" although its values are drill-pipe pressures (the choke is
adjusted to hold them), it seeded ICP 1200 / FCP 800 psi / 1500 strokes that a case would have captured as
entered values, and its "Cum. Volume" column was always empty. Now nothing is seeded (an un-entered value is
NOT ASSESSED), the volume column needs an entered pump output, and a case re-runs the schedule rows.
The Kill Sheet stays a TRAINING AID. Goldens are written out here. Synthetic data only; offscreen Qt.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from core import dp_schedule  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m128.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, ids
    manager.close()


@pytest.fixture
def w13(app, env, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs import w13_Engineering_Calculator as w13_module
    manager, ids = env
    monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(w13_module.QMessageBox, "warning", lambda *a, **k: None)
    tab = w13_module.EngineeringCalculatorTab(manager)
    tab.on_well_changed(ids["A"][0], {"name": "SYN-A"})
    assert tab.calculator_finder.open_path("Well Control › Choke Schedule")
    yield tab
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _fill(w13, icp=1150.0, fcp=760.0, strokes=1300.0, intervals=10, output=0.0):
    w13.cs_icp.setValue(icp)
    w13.cs_fcp.setValue(fcp)
    w13.cs_strokes.setValue(strokes)
    w13.cs_intervals.setValue(intervals)
    w13.cs_pump_output.setValue(output)


def _value(case, field_id):
    return next(v["value"] for v in case["results"].values() if isinstance(v, dict) and v.get("field_id") == field_id)


# ---- method -------------------------------------------------------------------------------------------
def test_schedule_golden_is_linear_from_icp_to_fcp():
    out = dp_schedule.schedule(1150.0, 760.0, 1300.0, 10, 0.1)
    rows = out["rows"]
    assert len(rows) == 11 and rows[0]["dp_psi"] == 1150.0 and rows[-1]["dp_psi"] == pytest.approx(760.0)
    assert rows[4]["strokes"] == pytest.approx(520.0) and rows[4]["dp_psi"] == pytest.approx(1150.0 - 4 * 39.0)
    assert rows[4]["cum_volume_bbl"] == pytest.approx(52.0) and rows[4]["percent_to_bit"] == pytest.approx(40.0)
    res = out["results"]
    assert res["pressure_step_psi"] == pytest.approx(39.0) and res["strokes_per_step"] == pytest.approx(130.0)
    assert res["psi_per_100_strokes"] == pytest.approx(30.0) and res["kill_mud_to_bit_bbl"] == pytest.approx(130.0)
    # exact rows (not rounded): 7 intervals of 1000 strokes
    assert dp_schedule.schedule(1000.0, 900.0, 1000.0, 7)["rows"][1]["strokes"] == pytest.approx(1000.0 / 7)


def test_nothing_is_assumed():
    out = dp_schedule.schedule(1150.0, 760.0, 1300.0, 10)          # no pump output: volumes unknown, not 0
    assert all(r["cum_volume_bbl"] is None for r in out["rows"]) and out["results"]["kill_mud_to_bit_bbl"] is None
    for bad in ((0, 760, 1300, 10), (1150, None, 1300, 10), (1150, 760, 0, 10), (1150, 760, 1300, 0),
                (1150, 760, 1300, 2.5), (1150, float("nan"), 1300, 10), (1150, 760, 1300, 21)):
        with pytest.raises(ValueError):
            dp_schedule.schedule(*bad)


# ---- page ---------------------------------------------------------------------------------------------
def test_page_is_not_seeded_and_says_drill_pipe_pressure(w13):
    assert (w13.cs_icp.value(), w13.cs_fcp.value(), w13.cs_strokes.value()) == (0.0, 0.0, 0.0)
    assert w13.cs_icp.text() == "Not entered"
    w13._wc_calc_choke()
    assert w13.cs_table.rowCount() == 0 and w13.cs_status.text().startswith("NOT ASSESSED")
    assert w13.cs_result.text() == ""
    assert w13.case_bar.save_case("SYN nothing entered") is None             # no result, no case
    header = [w13.cs_table.horizontalHeaderItem(c).text() for c in range(4)]
    assert header[1] == "Drill-pipe pressure (psi)"
    from tabs import w13_Engineering_Calculator as w13_module
    import inspect
    assert "Choke Pressure Schedule" not in inspect.getsource(w13_module)


def test_page_rows_and_volume_column(w13):
    _fill(w13)
    w13._wc_calc_choke()
    assert w13.cs_table.rowCount() == 11
    assert [w13.cs_table.item(4, c).text() for c in range(4)] == ["520", "994", "40%", "—"]
    assert "[WORKSHEET]" in w13.cs_result.text() and "bbl" not in w13.cs_result.text()
    w13.cs_pump_output.setValue(0.1)
    w13._wc_calc_choke()
    assert w13.cs_table.item(4, 3).text() == "52.0" and "130.0 bbl to the bit" in w13.cs_result.text()
    w13.cs_icp.setValue(0.0)                                   # a later invalid entry leaves no stale schedule
    w13._wc_calc_choke()
    assert w13.cs_table.rowCount() == 0 and w13.cs_result.text() == "" and w13.cs_rows == []
    assert w13.case_bar.save_case("SYN stale") is None


# ---- case ---------------------------------------------------------------------------------------------
def test_case_is_a_worksheet_that_reruns_and_reopens(w13, env):
    manager, _ = env
    _fill(w13, output=0.1)
    w13._wc_calc_choke()
    w13.case_bar.refresh()
    assert "Class: WORKSHEET" in w13.case_bar.contract_label.text()
    case = w13.case_bar.save_case("SYN DP schedule")
    assert case["method_version"] == "M128 drill-pipe pressure schedule v1"
    assert _value(case, "psi_per_100_strokes") == pytest.approx(30.0)
    entry = next(e for e in ch.load_history(manager, sources=["Calculation case"]) if e.record_id == case["id"])
    assert entry.scope == "W13 CALCULATOR — WORKSHEET" and ch.recalculate_entry(entry)["status"] == "MATCH"
    _fill(w13, 0.0, 0.0, 0.0, 5, 0.0)
    assert w13.case_bar.reopen(case["id"]) == []
    assert (w13.cs_icp.value(), w13.cs_fcp.value(), w13.cs_strokes.value(), w13.cs_intervals.value(),
            w13.cs_pump_output.value()) == (1150.0, 760.0, 1300.0, 10, 0.1)
    changed = {k: (dict(v) if isinstance(v, dict) else v) for k, v in case["inputs"].items()}
    key = next(k for k, v in changed.items() if isinstance(v, dict) and v.get("field_id") == "fcp")
    changed[key] = dict(changed[key], value=800.0)
    outcome = contracts.verify_case(case["method"], case["method_version"], changed, case["results"])
    assert outcome["status"] == "DIFFERENT" and "psi_per_100_strokes" in {d["field_id"] for d in outcome["differences"]}


def test_case_without_pump_output_stores_unknown_volume(w13):
    _fill(w13)
    w13._wc_calc_choke()
    case = w13.case_bar.save_case("SYN DP schedule no volume")
    assert _value(case, "kill_mud_to_bit_bbl") is None
    assert ch.recalculate_entry(next(e for e in ch.load_history(w13.db, sources=["Calculation case"])
                                     if e.record_id == case["id"]))["status"] == "MATCH"


def test_registry_after_m128():
    assert contracts.CONTRACT_REGISTRY_VERSION == "M128 calculator contracts v6"
    assert len(contracts.CONTRACTS) == 23 and contracts.classification_violations() == []
    assert set(contracts.NOT_SUPPORTED) == {"Well Control › Kill Sheet", "Directional › Multi-Survey",
                                            "Directional › Anti-Collision", "DP Database"}
    assert contracts.leaf_class("Well Control › Kill Sheet")[0] == contracts.CLASS_TRAINING     # unchanged
    assert contracts.leaf_class("Well Control › Choke Schedule")[0] == contracts.CLASS_WORKSHEET
