"""M372: drill-off test - founder point and per-step MSE (SYNTHETIC, SCREENING).

Golden values by hand (closed forms written here, not the production module):
8.5 in bit: A_b = pi/4 x 8.5^2 = 56.7450 in^2. RPM 120, torque 8000 ft·lbf.
Steps WOB 10/15/20/25/30 klbf, ROP 40/60/80/88/90 ft/h -> slopes 4, 4, 1.6, 0.4 ft/h per klbf.
* fraction 0.5: 1.6 < 2.0 -> founder at 20 klbf / 80 ft/h; fraction 0.3: 0.4 < 1.2 -> 25 klbf; 0.05: none.
* MSE at 20 klbf = 20000/56.745 + 120 pi x 120 x 8000 / (56.745 x 80) = 352.45 + 79723.2 = 80075.7 psi.
* drilling efficiency with CCS 20 000 psi = 20000 / 80075.7 = 0.24976.
* MSE at 30 klbf = 30000/56.745 + 361 911 475 / (56.745 x 90) = 528.7 + 70865.0 = 71393.7 psi (lowest step).
"""
from __future__ import annotations

import copy
import dataclasses
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import mse_drilloff as mdo  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

D = 8.5
AREA = math.pi / 4 * D ** 2
PARAMS = {"bit_diameter_in": D, "founder_slope_fraction": 0.5, "rpm_tolerance_rpm": 5.0, "ccs_psi": 20000.0}
STEPS = [{"wob_klbf": w, "rpm": 120.0, "torque_ft_lbf": 8000.0, "rop_ft_hr": r}
         for w, r in ((10, 40), (15, 60), (20, 80), (25, 88), (30, 90))]


def _hand_mse(wob_klbf, rpm, torque, rop):
    return wob_klbf * 1000 / AREA + 120 * math.pi * rpm * torque / (AREA * rop)


def test_founder_mse_and_efficiency_match_the_hand_values():
    r = mdo.evaluate(PARAMS, STEPS)
    assert AREA == pytest.approx(56.7450, abs=1e-4)
    assert r["status"] == mdo.COMPUTED and r["founder"]["status"] == mdo.FOUNDER
    assert (r["founder"]["wob_klbf"], r["founder"]["rop_ft_hr"]) == (20.0, 80.0)
    assert r["founder"]["slopes"] == pytest.approx([4.0, 4.0, 1.6, 0.4])
    step = r["steps"][2]
    assert step["mse_psi"] == pytest.approx(80075.7, abs=0.2)
    assert step["mse_psi"] == pytest.approx(_hand_mse(20, 120, 8000, 80), abs=0.1)
    assert step["efficiency"] == pytest.approx(20000 / 80075.7, rel=1e-5)
    # constant torque: the rotary term falls as ROP rises, so the lowest MSE is the last step (528.7 + 70865.0)
    assert r["lowest_mse_wob_klbf"] == 30.0 and r["lowest_mse_psi"] == pytest.approx(71393.7, abs=0.2)
    assert [row["mse_psi"] for row in r["steps"]] == pytest.approx(
        [_hand_mse(w["wob_klbf"], 120, 8000, w["rop_ft_hr"]) for w in STEPS], abs=0.1)
    assert any("Founder at WOB 20 klbf" in line for line in mdo.summary_lines(r))


@pytest.mark.parametrize("fraction, status, wob", [(0.3, mdo.FOUNDER, 25.0), (0.05, mdo.NO_FOUNDER, None)])
def test_the_declared_fraction_moves_the_founder(fraction, status, wob):
    founder = mdo.evaluate(dict(PARAMS, founder_slope_fraction=fraction), STEPS)["founder"]
    assert founder["status"] == status and founder.get("wob_klbf") == wob
    if status == mdo.NO_FOUNDER:
        assert "still on the linear trend" in founder["reason"]


def test_entry_order_does_not_matter_and_empty_rows_are_not_steps():
    shuffled = [STEPS[3], {}, STEPS[0], STEPS[4], {"wob_klbf": "", "rpm": None}, STEPS[2], STEPS[1]]
    r = mdo.evaluate(PARAMS, shuffled)
    assert [s["wob_klbf"] for s in r["steps"]] == [10, 15, 20, 25, 30]
    assert r["founder"]["wob_klbf"] == 20.0 and len(r["inputs"]["steps"]) == 5


def test_missing_torque_blocks_mse_for_that_step_only_and_zero_torque_is_a_value():
    steps = copy.deepcopy(STEPS)
    steps[1]["torque_ft_lbf"] = None
    steps[3]["torque_ft_lbf"] = 0.0
    r = mdo.evaluate(dict(PARAMS, ccs_psi=None), steps)
    assert r["steps"][1]["status"] == mdo.NOT_ASSESSED and r["steps"][1]["mse_psi"] is None
    assert "torque_ft_lbf" in r["steps"][1]["reason"]
    assert r["steps"][3]["mse_psi"] == pytest.approx(25000 / AREA, abs=0.1)
    assert r["steps"][0]["efficiency"] is None and r["steps"][0]["efficiency_reason"] == "no CCS declared"
    assert r["founder"]["status"] == mdo.FOUNDER                       # the founder uses WOB, RPM and ROP only


def test_founder_not_assessed_cases():
    varied = copy.deepcopy(STEPS)
    varied[4]["rpm"] = 130.0
    founder = mdo.evaluate(PARAMS, varied)["founder"]
    assert founder["status"] == mdo.NOT_ASSESSED and "not a drill-off test" in founder["reason"]
    assert mdo.evaluate(dict(PARAMS, rpm_tolerance_rpm=10.0), varied)["founder"]["status"] == mdo.FOUNDER
    assert mdo.evaluate(PARAMS, STEPS[:2])["founder"]["status"] == mdo.NOT_ASSESSED
    falling = [dict(STEPS[0], rop_ft_hr=60.0), dict(STEPS[1], rop_ft_hr=50.0), STEPS[2]]
    founder = mdo.evaluate(PARAMS, falling)["founder"]
    assert founder["status"] == mdo.NOT_ASSESSED and "does not rise" in founder["reason"]
    no_rop = copy.deepcopy(STEPS)
    for step in no_rop[2:]:
        step["rop_ft_hr"] = None
    assert mdo.evaluate(PARAMS, no_rop)["founder"]["status"] == mdo.NOT_ASSESSED


def test_required_inputs_and_refusals():
    assert mdo.evaluate(dict(PARAMS, founder_slope_fraction=None), STEPS)["status"] == mdo.NOT_ASSESSED
    assert mdo.evaluate(PARAMS, [{}])["reason"] == "no test steps entered"
    for change, message in ((dict(founder_slope_fraction=1.0), "fraction"), (dict(bit_diameter_in=0.0), "diameter"),
                            (dict(ccs_psi=0.0), "CCS"), (dict(extra=1), "unknown input"),
                            (dict(rpm_tolerance_rpm=-1.0), "tolerance")):
        with pytest.raises(mdo.DrillOffError, match=message):
            mdo.evaluate(dict(PARAMS, **change), STEPS)
    with pytest.raises(mdo.DrillOffError, match="same WOB"):
        mdo.evaluate(PARAMS, STEPS + [STEPS[0]])
    with pytest.raises(mdo.DrillOffError, match="negative"):
        mdo.evaluate(PARAMS, [dict(STEPS[0], rop_ft_hr=-1.0)])
    with pytest.raises(mdo.DrillOffError, match="not a number"):
        mdo.evaluate(PARAMS, [dict(STEPS[0], wob_klbf="1,5")])


def test_case_saves_and_replays_and_tampering_is_caught(db):  # noqa: F811
    r = mdo.evaluate(PARAMS, STEPS)
    case = mdo.save_case(db, r, well_id=None)
    assert case["method"] == mdo.METHOD_ID and case["inputs"]["ccs_psi"]["source"] == "DECLARED"
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    tampered = copy.deepcopy(entry.inputs)
    tampered["steps"]["value"][2]["rop_ft_hr"] = 70.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    changed = copy.deepcopy(entry.results)
    changed["founder_wob_klbf"]["value"] = 25.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), db)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["founder_wob_klbf"]
    with pytest.raises(ValueError, match="not computed"):
        mdo.save_case(db, mdo.evaluate(PARAMS, []), well_id=None)


def test_w13_bit_page_button_opens_the_dialog_with_page_values(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    try:
        assert tab.mse_drilloff_btn.text().startswith("📈 Drill-off test")
        tab.bit_od.setValue(D)
        tab.bit_wob.setValue(10.0)
        tab.bit_rpm.setValue(120.0)
        tab.bit_tq.setValue(8000.0)
        tab.bit_rop.setValue(0.0)                                     # 0 on the page = not entered
        dialog = tab.mse_drilloff_dialog()
        assert dialog.edits["bit_diameter_in"].text() == "8.5" and dialog.edits["ccs_psi"].text() == ""
        assert dialog.table.item(0, 0) is None                        # incomplete page step is not copied
        tab.bit_rop.setValue(40.0)
        dialog.deleteLater()
        dialog = tab.mse_drilloff_dialog()
        assert [dialog.table.item(0, c).text() for c in range(4)] == ["10", "120", "8000", "40"]
        assert dialog.run()["founder"]["status"] == mdo.NOT_ASSESSED
        for row, step in enumerate(STEPS[1:], start=1):
            dialog.set_step(row, step)
        result = dialog.run()
        assert result["founder"]["wob_klbf"] == 20.0 and "Founder at WOB 20 klbf" in dialog.summary.text()
        assert "efficiency NOT ASSESSED" in dialog.summary.text()
        dialog.edits["ccs_psi"].setText("20000")
        assert dialog.run()["steps"][2]["efficiency"] == pytest.approx(0.24976, abs=1e-5)
        case = dialog.save()
        assert case and "Saved as calculation case" in dialog.summary.text()
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
