"""M371: casing axial-load components and wear-reduced ratings (SYNTHETIC, SCREENING).

Golden values by hand (independent closed forms written here, not the production module):
9-5/8 in casing, ID 8.681 in: A_s = pi/4 (9.625^2 - 8.681^2) = 13.5724 in^2.
* DLS 3 deg/100 ft, E 30e6 psi: kappa = 3 pi/180/1200 = 4.36332e-5 rad/in, sigma_b = 30e6 x 4.8125 x kappa
  = 6299.5 psi (the textbook shortcut 218.2 x OD x DLS gives 6300 psi).
* dT = +100 degF, alpha 6.9e-6 /degF: dF_T = -30e6 x 6.9e-6 x 100 x 13.5724 = -280 949 lbf.
* dPi = +1000 psi, dPo = 0, nu 0.3: dF_B = 0.6 x pi/4 x 8.681^2 x 1000 = 35 512 lbf.
* Barlow on a 10 % worn wall (0.472 x 0.9 = 0.4248 in), Yp 80 000: 0.875 x 2 x 80 000 x 0.4248 / 9.625 = 6178.9 psi.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import casing_axial_loads as cal  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

OD, ID, YP = 9.625, 8.681, 80000.0
AREA = math.pi / 4 * (OD ** 2 - ID ** 2)
FULL = {"od_in": OD, "id_in": ID, "yield_psi": YP, "base_axial_load_lbf": 300000.0, "youngs_modulus_psi": 30e6,
        "dls_deg_per_100ft": 3.0, "expansion_per_degf": 6.9e-6, "delta_temperature_degf": 100.0,
        "poisson_ratio": 0.3, "delta_internal_psi": 1000.0, "delta_external_psi": 0.0, "wear_percent": 10.0}


def test_components_match_the_hand_values():
    r = cal.evaluate(FULL)
    assert r["status"] == cal.COMPUTED and r["steel_area_in2"] == pytest.approx(13.5724, abs=1e-4)
    bending = r["components"]["bending"]
    assert bending["stress_psi"] == pytest.approx(6299.5, abs=0.5)
    assert bending["stress_psi"] == pytest.approx(218.2 * OD * 3.0, rel=1e-3)
    assert bending["value"] == pytest.approx(6299.5 * AREA, rel=1e-4)
    assert r["components"]["temperature"]["value"] == pytest.approx(-280949, abs=2)
    assert r["components"]["ballooning"]["value"] == pytest.approx(35512, abs=1)
    total = 300000 - 280949 + 35512
    assert r["total_axial_lbf"] == pytest.approx(total, abs=3)
    assert r["max_fibre_stress_psi"] == pytest.approx(total / AREA + 6299.5, abs=1)
    assert r["utilisation"] == pytest.approx((total / AREA + 6299.5) / YP, rel=1e-4)
    assert r["rating_wall_in"] == pytest.approx(0.472 * 0.9, abs=1e-9)
    assert r["burst_psi"] == pytest.approx(0.875 * 2 * YP * 0.4248 / OD, abs=0.1)


def test_external_pressure_increase_reduces_tension():
    r = cal.evaluate(dict(FULL, delta_internal_psi=0.0, delta_external_psi=1000.0))
    assert r["components"]["ballooning"]["value"] == pytest.approx(-0.6 * math.pi / 4 * OD ** 2 * 1000, abs=1)


def test_missing_inputs_are_never_zero_and_a_partial_sum_is_not_a_total():
    r = cal.evaluate({k: FULL[k] for k in ("od_in", "id_in", "yield_psi", "base_axial_load_lbf",
                                           "youngs_modulus_psi", "dls_deg_per_100ft")})
    assert r["components"]["bending"]["status"] == cal.COMPUTED
    assert r["components"]["temperature"]["status"] == cal.NOT_ASSESSED
    assert r["components"]["temperature"]["value"] is None and "expansion_per_degf" in \
        r["components"]["temperature"]["reason"]
    assert r["components"]["ballooning"]["status"] == cal.NOT_ASSESSED
    assert r["total_status"] == cal.NOT_ASSESSED and r["total_axial_lbf"] is None
    assert "partial sum is not a total" in r["total_reason"]
    assert r["wear"]["status"] == cal.NOT_ASSESSED and r["rating_wall_in"] == pytest.approx((OD - ID) / 2)
    no_base = cal.evaluate(dict(FULL, base_axial_load_lbf=None))
    assert no_base["total_status"] == cal.NOT_ASSESSED and "base axial load" in no_base["total_reason"]
    assert cal.evaluate({"od_in": OD})["status"] == cal.NOT_ASSESSED


def test_zero_temperature_change_is_a_value_not_a_missing_input():
    r = cal.evaluate(dict(FULL, delta_temperature_degf=0.0))
    assert r["components"]["temperature"]["status"] == cal.COMPUTED
    assert r["components"]["temperature"]["value"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("change, message", [
    (dict(id_in=10.0), "OD > ID"), (dict(poisson_ratio=0.6), "Poisson"), (dict(wear_percent=100.0), "wear"),
    (dict(youngs_modulus_psi=-1.0), "Young"), (dict(dls_deg_per_100ft="1,5"), "not a number"),
    (dict(extra=1.0), "unknown input"),
])
def test_invalid_inputs_are_refused(change, message):
    with pytest.raises(cal.AxialLoadError, match=message):
        cal.evaluate(dict(FULL, **change))


def test_case_saves_and_replays_and_tampering_is_caught(db):  # noqa: F811
    r = cal.evaluate(FULL)
    case = cal.save_case(db, r, well_id=None)
    assert case["method"] == cal.METHOD_ID and case["inputs"]["poisson_ratio"]["source"] == "DECLARED"
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    tampered = copy.deepcopy(entry.inputs)
    tampered["delta_temperature_degf"]["value"] = 50.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    changed = copy.deepcopy(entry.results)
    changed["temperature_lbf"]["value"] += 10.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), db)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["temperature_lbf"]
    with pytest.raises(ValueError, match="not computed"):
        cal.save_case(db, cal.evaluate({"od_in": OD}), well_id=None)


def test_w13_casing_page_button_opens_the_dialog_with_page_values(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    try:
        assert tab.csg_axial_loads_btn.text().startswith("📐 Axial loads")
        tab.csg_od.setValue(OD)
        tab.csg_id_calc.setValue(ID)
        tab.csg_yield.setValue(YP)
        tab.csg_axial.setValue(0.0)                                   # 0 on the page = not entered
        dialog = tab.csg_axial_loads_dialog()
        assert dialog.edits["od_in"].text() == "9.625" and dialog.edits["base_axial_load_lbf"].text() == ""
        assert dialog.edits["youngs_modulus_psi"].text() == ""        # no steel default
        result = dialog.run()
        assert result["status"] == cal.COMPUTED and "Total: NOT ASSESSED" in dialog.summary.text()
        for key in ("base_axial_load_lbf", "youngs_modulus_psi", "dls_deg_per_100ft", "expansion_per_degf",
                    "delta_temperature_degf", "poisson_ratio", "delta_internal_psi", "delta_external_psi"):
            dialog.edits[key].setText(f"{FULL[key]:g}")
        dialog.edits["poisson_ratio"].setText("0,3")
        assert dialog.run() is None and "not a number" in dialog.summary.text()
        dialog.edits["poisson_ratio"].setText("0.3")
        result = dialog.run()
        assert result["total_status"] == cal.COMPUTED and "% of yield" in dialog.summary.text()
        case = dialog.save()
        assert case and "Saved as calculation case" in dialog.summary.text()
        dialog.deleteLater()
    finally:
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
