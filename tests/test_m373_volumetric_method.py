"""M373: volumetric method worksheet and gas migration - TRAINING AID (P11), SYNTHETIC.

Golden values by hand (closed forms written here, not the production module):
mud 90 lb/ft^3 -> G = 90 / 144 = 0.625 psi/ft. Annular capacity 0.0459 bbl/ft -> H = 0.625 / 0.0459 = 13.6166
psi/bbl. Pw 100 psi -> dV = 100 x 0.0459 / 0.625 = 7.344 bbl per cycle.
SICP 500, Ps 100, Pw 100 -> hold 700, 800, 900, 1000 psi; with a 950 psi limit cycle 4 exceeds and the table stops.
Rise of 150 psi in 0.5 h -> 300 psi/h / 0.625 = 480 ft/h.
"""
from __future__ import annotations

import copy
import dataclasses
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import well_control_volumetric as wcv  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

BASE = {"sicp_psi": 500.0, "mud_density_pcf": 90.0, "annular_capacity_bbl_ft": 0.0459, "safety_margin_psi": 100.0,
        "working_range_psi": 100.0, "cycles": 5}


def test_schedule_matches_the_hand_values():
    r = wcv.evaluate(BASE)
    assert r["status"] == wcv.COMPUTED and r["gradient_psi_ft"] == pytest.approx(0.625)
    assert r["hydrostatic_psi_per_bbl"] == pytest.approx(13.6166, abs=1e-4)
    assert r["volume_per_cycle_bbl"] == pytest.approx(7.344, abs=1e-9)
    assert [row["hold_casing_psi"] for row in r["schedule"]] == [700, 800, 900, 1000, 1100]
    assert [row["cumulative_bbl"] for row in r["schedule"]] == pytest.approx([7.344 * k for k in range(1, 6)])
    assert {row["state"] for row in r["schedule"]} == {wcv.NO_LIMIT} and r["stopped_at_cycle"] is None
    assert r["migration"]["status"] == wcv.NOT_ASSESSED
    assert wcv.LABEL.startswith("TRAINING AID - NOT FOR OPERATIONAL WELL CONTROL")


def test_a_declared_limit_stops_the_schedule_at_the_first_exceeding_cycle():
    r = wcv.evaluate(dict(BASE, casing_limit_psi=950.0))
    assert [row["state"] for row in r["schedule"]] == [wcv.WITHIN] * 3 + [wcv.EXCEEDS]
    assert r["stopped_at_cycle"] == 4 and len(r["schedule"]) == 4
    assert any(line.startswith("STOP: cycle 4") for line in wcv.summary_lines(r))
    at_limit = wcv.evaluate(dict(BASE, casing_limit_psi=900.0))
    assert at_limit["schedule"][2]["state"] == wcv.WITHIN and at_limit["stopped_at_cycle"] == 4


def test_migration_rate_and_zero_rise_is_a_value():
    r = wcv.evaluate(dict(BASE, pressure_rise_psi=150.0, rise_duration_h=0.5))
    assert r["migration"]["status"] == wcv.COMPUTED and r["migration"]["value"] == pytest.approx(480.0)
    zero = wcv.evaluate(dict(BASE, pressure_rise_psi=0.0, rise_duration_h=1.0))
    assert zero["migration"]["status"] == wcv.COMPUTED and zero["migration"]["value"] == 0.0
    half = wcv.evaluate(dict(BASE, pressure_rise_psi=150.0))
    assert half["migration"]["status"] == wcv.NOT_ASSESSED and "rise_duration_h" in half["migration"]["reason"]


def test_missing_inputs_and_refusals():
    r = wcv.evaluate({k: v for k, v in BASE.items() if k != "annular_capacity_bbl_ft"})
    assert r["status"] == wcv.NOT_ASSESSED and "annular_capacity_bbl_ft" in r["reason"]
    for change, message in ((dict(cycles=2.5), "whole number"), (dict(cycles=51), "whole number"),
                            (dict(working_range_psi=0.0), "must be > 0"), (dict(sicp_psi=-1.0), "negative"),
                            (dict(casing_limit_psi=0.0), "limit"), (dict(mud_density_pcf="12 ppg"), "not a number"),
                            (dict(rise_duration_h=0.0, pressure_rise_psi=10.0), "duration"),
                            (dict(mud_weight_ppg=12.0), "unknown input")):
        with pytest.raises(wcv.VolumetricError, match=message):
            wcv.evaluate(dict(BASE, **change))


def test_case_saves_and_replays_and_tampering_is_caught(db):  # noqa: F811
    r = wcv.evaluate(dict(BASE, casing_limit_psi=950.0, pressure_rise_psi=150.0, rise_duration_h=0.5))
    case = wcv.save_case(db, r, well_id=None)
    assert case["method"] == wcv.METHOD_ID and "TRAINING AID" in case["note"]
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    tampered = copy.deepcopy(entry.inputs)
    tampered["casing_limit_psi"]["value"] = 2000.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    changed = copy.deepcopy(entry.results)
    changed["volume_per_cycle_bbl"]["value"] = 8.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), db)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["volume_per_cycle_bbl"]
    with pytest.raises(ValueError, match="not computed"):
        wcv.save_case(db, wcv.evaluate({"sicp_psi": 500.0}), well_id=None)


def test_w13_kill_sheet_button_opens_the_training_aid_with_page_values(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    try:
        assert "TRAINING AID" in tab.wc_volumetric_btn.text()
        tab.wc_sicp.setValue(500.0)
        tab.wc_mw.setValue(90.0)
        dialog = tab.wc_volumetric_dialog()
        assert dialog.edits["sicp_psi"].text() == "500" and dialog.edits["mud_density_pcf"].text() == "90"
        assert dialog.edits["annular_capacity_bbl_ft"].text() == ""      # never inferred from the string table
        assert dialog.run()["status"] == wcv.NOT_ASSESSED and not dialog.save_btn.isEnabled()
        for key in ("annular_capacity_bbl_ft", "safety_margin_psi", "working_range_psi", "cycles"):
            dialog.edits[key].setText(f"{BASE[key]:g}")
        dialog.edits["casing_limit_psi"].setText("950")
        result = dialog.run()
        assert result["stopped_at_cycle"] == 4 and "STOP: cycle 4" in dialog.summary.text()
        assert "TRAINING AID" in dialog.summary.text()
        case = dialog.save()
        assert case and "Saved as calculation case" in dialog.summary.text()
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
