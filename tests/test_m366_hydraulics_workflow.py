"""M366 — hydraulics workflow: budget, pump limits, flow / nozzle sensitivity, plan vs actual, persistence, replay.

SYNTHETIC data only. Every expected value is an independent closed form written out here (API field-unit
formulas), never a value read back from the engine under test:

* bit ΔP = Q² · MW / (10858 · TFA²) psi; TFA = n · π/4 · (d/32)² in²
* bit HHP = ΔP · Q / 1714; HSI = HHP / (π/4 · Dbit²); jet velocity = Q / (3.117 · TFA) ft/s
* ECD = MW + APL / (0.052 · TVD ft) ppg; MW ppg = pcf / 7.48052 (P8 divisor)
* required pump HHP = SPP · Q / 1714
"""
from __future__ import annotations

import copy
import dataclasses
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import history_replay as hr  # noqa: E402
from core import hydraulics_workflow as hw  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

FT = 3.28084
MW_PPG = 90.0 / 7.48052                       # page default 90 pcf, P8 divisor
PIPES = [{"type": "Drill Pipe", "od": 5.0, "id": 4.276, "length": 2800.0, "weight": 19.5},
         {"type": "Drill Collar", "od": 6.5, "id": 2.8125, "length": 200.0, "weight": 90.0}]
BORES = [{"type": "9 5/8 Casing", "od": 9.625, "id": 8.835, "from": 0.0, "to": 1000.0},
         {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
PUMP = {"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0, "max_pressure": 3000.0, "hp": 1000.0}  # 420 gpm


def _tfa(n, size):
    return n * math.pi / 4.0 * (size / 32.0) ** 2


def _bit_dp(q, tfa):
    return q ** 2 * MW_PPG / (10858.0 * tfa ** 2)


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


def _fill(w13, pump=None, pipes=None, bores=None, confirm=True):
    assert w13.calculator_finder.open_path("Hydraulics")
    w13.hy_pumps[:] = [dict(pump or PUMP)]
    w13._hy_refresh_pump_table()
    w13.hy_pipe_rows = pipes or PIPES
    w13.hy_csg_rows = bores or BORES
    w13.hy_nzl_rows = [{"size": 12, "qty": 3}]
    w13._hy_update_tfa()
    w13.hy_bit_diameter.setValue(8.5)
    w13.hy_model.setCurrentText("Bingham Plastic")
    w13.hy_wt.setCurrentText("Vertical")
    w13.hy_bit_dep.setValue(3000.0)
    w13.hy_confirm_defaults.setChecked(confirm)
    return w13._hy_values()


# ---- base point and budget --------------------------------------------------------------------------------
def test_base_point_bit_hydraulics_match_independent_closed_forms(w13):
    r = hw.evaluate(_fill(w13))
    assert r["status"] == "COMPUTED" and r["label"].startswith("SCREENING")
    base, q, tfa = r["base"], 420.0, _tfa(3, 12)
    assert base["flow_gpm"] == pytest.approx(q)
    assert base["tfa_in2"] == pytest.approx(tfa, abs=1e-4)
    assert base["bit_loss_psi"] == pytest.approx(_bit_dp(q, tfa), rel=1e-3)
    hhp = _bit_dp(q, tfa) * q / 1714.0
    assert base["bit_hhp"] == pytest.approx(hhp, rel=1e-3)
    assert base["hsi"] == pytest.approx(hhp / (math.pi / 4 * 8.5 ** 2), rel=1e-2)
    assert base["jet_velocity_fps"] == pytest.approx(q / (3.117 * tfa), rel=1e-3)


def test_budget_splits_drill_pipe_and_bha_and_closes_on_the_engine_total(w13):
    base = hw.evaluate(_fill(w13))["base"]
    rows = {row["group"]: row for row in base["budget"]["rows"]}
    assert rows["drill_pipe"]["loss_psi"] > 0 and rows["bha"]["loss_psi"] > 0
    assert rows["hwdp"]["loss_psi"] is None and rows["unclassified_string"]["loss_psi"] is None   # none supplied
    assert base["budget"]["closes"]
    parts = sum(r["loss_psi"] for r in rows.values() if r["loss_psi"] is not None)
    assert parts == pytest.approx(base["spp_psi"], abs=0.1)
    assert sum(r["share_pct"] for r in rows.values() if r["share_pct"] is not None) == pytest.approx(100.0, abs=0.01)
    # independent DC bore turbulent check: 420 gpm in a 2.8125 in bore is turbulent (Bingham rows of M126); the
    # BHA bore loss per foot is far above the drill-pipe bore loss per foot (ID ratio 1.52 → ≈ 1.52^4.75 ≈ 7.3×)
    per_ft_dp = rows["drill_pipe"]["loss_psi"] / (2800 * FT)
    per_ft_bha = rows["bha"]["loss_psi"] / (200 * FT)
    assert 5.0 < per_ft_bha / per_ft_dp < 10.0


def test_unknown_component_type_is_unclassified_not_guessed(w13):
    pipes = [dict(PIPES[0]), dict(PIPES[1], type="Other")]
    rows = {row["group"]: row for row in hw.evaluate(_fill(w13, pipes=pipes))["base"]["budget"]["rows"]}
    assert rows["bha"]["loss_psi"] is None and rows["unclassified_string"]["loss_psi"] > 0


def test_ecd_matches_independent_form_and_is_withheld_without_complete_annular_geometry(w13):
    base = hw.evaluate(_fill(w13))["base"]
    assert base["ecd_at_bit_ppg"] == pytest.approx(MW_PPG + base["annular_loss_psi"] / (0.052 * 3000 * FT), abs=2e-3)
    assert base["ecd_state"].startswith("ASSESSED")
    short = [BORES[0], dict(BORES[1], to=2500.0)]                  # the bore stops 500 m above the bit
    r = hw.evaluate(_fill(w13, bores=short))
    assert r["status"] == "NOT_ASSESSED" and r["base"]["status"] == "NOT_ASSESSED"
    assert "cover" in r["reason"] and "ecd_at_bit_ppg" not in r["base"]


def test_unconfirmed_inputs_are_not_assessed(w13):
    r = hw.evaluate(_fill(w13, confirm=False))
    assert r["status"] == "NOT_ASSESSED" and "not confirmed" in r["reason"] and r["base"] is None


# ---- pump limits ------------------------------------------------------------------------------------------
def test_pump_pressure_and_horsepower_limits_use_entered_ratings_only(w13):
    base = hw.evaluate(_fill(w13))["base"]
    pump = base["pumps"][0]
    assert pump["required_hhp"] == pytest.approx(base["spp_psi"] * 420.0 / 1714.0, rel=1e-9)
    assert pump["pressure_margin_psi"] == pytest.approx(3000.0 - base["spp_psi"])
    assert pump["pressure_status"] == ("WITHIN" if base["spp_psi"] <= 3000.0 else "EXCEEDED")
    assert "mechanical efficiency not applied" in pump["hp_status"]
    unrated = hw.evaluate(_fill(w13, pump=dict(PUMP, max_pressure=0.0, hp=0.0)))["base"]["pumps"][0]
    assert (unrated["pressure_status"], unrated["hp_status"]) == ("NOT ENTERED", "NOT ENTERED")
    assert unrated["max_pressure_psi"] is None and unrated["pressure_margin_psi"] is None   # 0 ≠ a 0 psi limit


def test_low_limit_is_exceeded():
    rows = hw.pump_limits({"pumps": [PUMP]}, 3500.0)
    assert rows[0]["pressure_status"] == "EXCEEDED" and rows[0]["pressure_margin_psi"] == pytest.approx(-500.0)
    assert rows[0]["required_hhp"] == pytest.approx(3500.0 * 420.0 / 1714.0)          # 857.6 hp ≤ 1000 hp
    assert rows[0]["hp_status"].startswith("WITHIN")


def test_sensitivity_flow_is_shared_between_pumps_in_page_proportion():
    pumps = [dict(PUMP, name="A", spm=100.0), dict(PUMP, name="B", spm=50.0)]          # 420 + 210 gpm on page
    rows = hw.pump_limits({"pumps": pumps}, 2000.0, total_flow_gpm=900.0)
    assert [r["flow_gpm"] for r in rows] == pytest.approx([600.0, 300.0])


# ---- sensitivity ------------------------------------------------------------------------------------------
def test_flow_sweep_reruns_the_frozen_inputs_and_flags_the_pump_limit(w13):
    r = hw.evaluate(_fill(w13), flow_rates=[300.0, 420.0, 520.0])
    sweep = {p["flow_gpm"]: p for p in r["flow_sweep"]}
    assert sweep[420.0]["spp_psi"] == pytest.approx(r["base"]["spp_psi"])               # same point as the base
    spp = [sweep[q]["spp_psi"] for q in (300.0, 420.0, 520.0)]
    assert spp == sorted(spp)
    for q, p in sweep.items():
        assert p["bit_loss_psi"] == pytest.approx(_bit_dp(q, _tfa(3, 12)), rel=1e-3)
        assert p["pump_status"] == ("EXCEEDED" if p["spp_psi"] > 3000.0 else "WITHIN")
    assert sweep[520.0]["pump_status"] == "EXCEEDED"                                    # bit ΔP alone ≈ 2729 psi


def test_nozzle_sweep_matches_independent_bit_formulas(w13):
    r = hw.evaluate(_fill(w13), nozzle_sets=[[(12, 3)], [(13, 3)], [(12, 2), (14, 1)]])
    for point, (pairs) in zip(r["nozzle_sweep"], ([(12, 3)], [(13, 3)], [(12, 2), (14, 1)]), strict=True):
        tfa = sum(_tfa(q, s) for s, q in pairs)
        assert point["tfa_in2"] == pytest.approx(tfa, abs=1e-4)
        assert point["bit_loss_psi"] == pytest.approx(_bit_dp(420.0, tfa), rel=1e-3)
        assert point["jet_velocity_fps"] == pytest.approx(420.0 / (3.117 * tfa), rel=1e-3)
    assert r["nozzle_sweep"][0]["spp_psi"] == pytest.approx(r["base"]["spp_psi"])
    # the non-bit losses do not depend on nozzles: SPP difference equals the bit ΔP difference
    d_spp = r["nozzle_sweep"][0]["spp_psi"] - r["nozzle_sweep"][1]["spp_psi"]
    assert d_spp == pytest.approx(_bit_dp(420.0, _tfa(3, 12)) - _bit_dp(420.0, _tfa(3, 13)), abs=0.2)


@pytest.mark.parametrize("text,expected", [("400, 450 500", [400.0, 450.0, 500.0]), ("400;400", [400.0]), ("", [])])
def test_flow_rate_parsing(text, expected):
    assert hw.parse_flow_rates(text) == expected


@pytest.mark.parametrize("text", ["abc", "-5", "0", "inf", ",".join(str(400 + i) for i in range(13))])
def test_bad_flow_rates_are_refused(text):
    with pytest.raises(hw.WorkflowError):
        hw.parse_flow_rates(text)


def test_nozzle_parsing_and_refusals():
    assert hw.parse_nozzle_sets("3x12+1x13; 4x12") == [[(12, 3), (13, 1)], [(12, 4)]]
    for bad in ("12", "3x0", "ax12", "3x12.5"):
        with pytest.raises(hw.WorkflowError):
            hw.parse_nozzle_sets(bad)


# ---- plan vs actual ---------------------------------------------------------------------------------------
def test_plan_vs_actual_classifies_only_against_a_declared_tolerance():
    assert hw.plan_vs_actual(2800.0, 2900.0, None)["status"] == "NOT CLASSIFIED"
    out = hw.plan_vs_actual(2800.0, 2900.0, 150.0)
    assert out["status"] == "WITHIN DECLARED TOLERANCE" and out["difference_psi"] == pytest.approx(100.0)
    assert out["difference_pct"] == pytest.approx(100.0 / 2800.0 * 100.0)
    assert hw.plan_vs_actual(2800.0, 3000.0, 150.0)["status"] == "OUTSIDE DECLARED TOLERANCE"
    assert hw.plan_vs_actual(2800.0, None, 150.0)["status"] == "NOT ENTERED"
    assert hw.plan_vs_actual(2800.0, -1.0, None)["status"] == "REFUSED"
    assert hw.plan_vs_actual(2800.0, 2900.0, -5.0)["status"] == "REFUSED"
    assert hw.plan_vs_actual(None, 2900.0, 100.0)["status"] == "NOT ASSESSED"


# ---- UI → service → persistence → history replay ----------------------------------------------------------
def test_w13_button_opens_dialog_runs_saves_and_history_replays_it(w13):
    _fill(w13)
    buttons = [b for b in w13.findChildren(QtWidgets.QPushButton) if "Budget & Sensitivity" in b.text()]
    assert len(buttons) == 1
    dialog = w13.hy_workflow_dialog()
    try:
        w13.hy_mw.setValue(95.0)                                    # a later page edit must not reach the dialog
        assert dialog.values["mw"] == 90.0
        dialog.flow_edit.setText("350, 450")
        dialog.nozzle_edit.setText("3x13")
        dialog.observed_edit.setText("2900")
        dialog.tolerance_edit.setText("200")
        result = dialog.run()
        assert result["status"] == "COMPUTED" and dialog.save_btn.isEnabled()
        assert dialog.flow_table.rowCount() == 2 and dialog.nozzle_table.rowCount() == 1
        assert dialog.budget_table.rowCount() == len(hw.GROUPS) + 1
        assert "Plan vs actual:" in dialog.summary.text()
        case = dialog.save()
    finally:
        dialog.deleteLater()
    assert case["method"] == hw.METHOD_ID and case["method_version"] == hw.METHOD_VERSION
    entry = next(e for e in ch.load_history(w13.db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert entry.inputs["values_sha256"]["value"] == result["values_sha256"]
    assert ch.recalculate_entry(entry, w13.db)["status"] == "MATCH"
    tampered = copy.deepcopy(entry.inputs)
    tampered["snapshot"]["value"]["values"]["mw"] = 100.0
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), w13.db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    changed = copy.deepcopy(entry.results)
    changed["base_spp_psi"]["value"] += 5.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), w13.db)
    assert out["status"] == "DIFFERENT"
    diff = next(d for d in out["differences"] if d["field_id"] == "base_spp_psi")
    assert diff["unit"] == "psi" and diff["tolerance"] == hr.FIELD_TOLERANCES["psi"]
    out = ch.recalculate_entry(dataclasses.replace(entry, version="M366 v0"), w13.db)
    assert out["status"] == "NOT_REPRODUCIBLE"


def test_dialog_refuses_bad_text_and_unconfirmed_page_opens_nothing(w13):
    _fill(w13, confirm=False)
    assert w13.hy_workflow_dialog() is None and "confirm" in w13.hy_warn.text()
    _fill(w13)
    dialog = w13.hy_workflow_dialog()
    try:
        dialog.observed_edit.setText("lots")
        assert dialog.run() is None and "Not run" in dialog.summary.text() and not dialog.save_btn.isEnabled()
    finally:
        dialog.deleteLater()


def test_a_not_assessed_workflow_is_not_saved(w13):
    r = hw.evaluate(_fill(w13, confirm=False))
    with pytest.raises(ValueError, match="Nothing to store"):
        hw.save_case(w13.db, r, well_id=None)
