"""M475-M478 (E6b part) and M482: robust (L1) drill-off v2 under its own method ID; Erge 2015 marked NOT VERIFIED.

INDEPENDENT expected values (input class: SYNTHETIC). Every expected breakpoint, slope and intercept is the hinge the
data were constructed on. A gross ROP outlier is then added; with the outlier count below the L1 breakdown for the
designed test, the exact least-absolute-deviations fit must return the constructing hinge, with the outlier as the only
non-zero residual. L1 optimality is checked independently by random coefficient perturbations and the subgradient
condition. Nothing is taken from the production module except the value under test.
"""
from __future__ import annotations

import copy
import dataclasses
import inspect
import os
import random

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import drilloff_fitted as df  # noqa: E402
from core import drilloff_robust as dr  # noqa: E402
from core import history_replay as hr  # noqa: E402
from core import hydraulics_hb_slot as hb  # noqa: E402
from core import mse_drilloff  # noqa: E402
from core import surge_swab as ss  # noqa: E402
from tests.test_m73_contracts_history import db  # noqa: E402,F401

PARAMS = {"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5, "wob_basis": "surface"}
WOBS = (8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0, 44.0)


def knee26(w):                       # lower slope 4, upper 0.4 ft/h/klbf, break 26 klbf, intercept 0
    return 4 * w if w <= 26 else 104 + 0.4 * (w - 26)


def knee30(w):                       # lower slope 2, upper 0.4, break 30 (a tested WOB), intercept 5
    return 5 + 2 * w if w <= 30 else 65 + 0.4 * (w - 30)


def steps(fn=knee26, wobs=WOBS, rpm=120.0, bumps=None):
    bumps = bumps or {}
    return [{"wob_klbf": w, "rpm": rpm, "rop_ft_hr": fn(w) + bumps.get(w, 0.0)} for w in wobs]


# ---- M475: the fit -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fn,wobs,knee,low,up,a", [
    (knee26, WOBS, 26.0, 4.0, 0.4, 0.0),                               # knee between tested WOB values
    (knee30, tuple(range(10, 65, 5)), 30.0, 2.0, 0.4, 5.0),            # knee on a tested WOB value
])
def test_exact_hinge_is_recovered(fn, wobs, knee, low, up, a):
    r = dr.evaluate(PARAMS, steps(fn, [float(w) for w in wobs]))
    assert r["status"] == dr.COMPUTED and r["founder_status"] == dr.FOUNDER
    assert r["breakpoint_wob_klbf"] == pytest.approx(knee, abs=1e-6)
    assert r["slope_below"] == pytest.approx(low, abs=1e-9) and r["slope_above"] == pytest.approx(up, abs=1e-9)
    assert r["intercept"] == pytest.approx(a, abs=1e-8)
    assert r["sum_abs_residuals"] == pytest.approx(0.0, abs=1e-8) and r["flagged_wob_klbf"] == []


def test_a_gross_outlier_next_to_the_knee_does_not_move_the_l1_breakpoint():
    gross = steps(bumps={16.0: 40.0})                         # the M423 stated-limitation case
    assert abs(df.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}, gross)["fitted_breakpoint_wob_klbf"]
               - 26.0) > 5.0                                  # least squares is pulled (M423, unchanged)
    r = dr.evaluate(PARAMS, gross)
    assert r["breakpoint_wob_klbf"] == pytest.approx(26.0, abs=1e-6)
    assert r["slope_below"] == pytest.approx(4.0, abs=1e-9) and r["slope_above"] == pytest.approx(0.4, abs=1e-9)
    assert r["sum_abs_residuals"] == pytest.approx(40.0, abs=1e-8)
    assert r["flagged_wob_klbf"] == [16.0] and r["steps_used"] == 10                 # flagged, never removed
    assert r["residuals"][2] == pytest.approx(40.0, abs=1e-8)
    assert any("flagged, not removed" in line for line in dr.summary_lines(r))


@pytest.mark.parametrize("bumps", [{35.0: 40.0}, {30.0: 40.0}, {35.0: -30.0, 50.0: 25.0}])
def test_outliers_at_and_after_the_knee(bumps):
    r = dr.evaluate(PARAMS, steps(knee30, [float(w) for w in range(10, 65, 5)], bumps=bumps))
    assert r["breakpoint_wob_klbf"] == pytest.approx(30.0, abs=1e-6)
    assert r["sum_abs_residuals"] == pytest.approx(sum(abs(b) for b in bumps.values()), abs=1e-8)
    assert sorted(r["flagged_wob_klbf"]) == sorted(bumps)


def test_fixed_breakpoint_fit_is_an_l1_minimum():
    rng = random.Random(475)
    xs = list(WOBS)
    ys = [knee26(x) + rng.uniform(-3, 3) for x in xs]
    coef, sad, vertex = dr.lad_hinge(xs, ys, 26.0)

    def sad_of(c):
        return sum(abs(y - (c[0] + c[1] * x + c[2] * max(x - 26.0, 0.0))) for x, y in zip(xs, ys))

    assert sad == pytest.approx(sad_of(coef), rel=1e-12)
    assert len(vertex) == 3 and all(abs(ys[i] - (coef[0] + coef[1] * xs[i] + coef[2] * max(xs[i] - 26.0, 0)))
                                    < 1e-9 for i in vertex)
    for _ in range(2000):
        trial = [c + rng.gauss(0, s) for c, s in zip(coef, (1.0, 0.05, 0.05))]
        assert sad_of(trial) >= sad - 1e-9


def _grid(xs):
    """The stated search grid, rebuilt here: GRID points per interval in [x_(2), x_(n-1)] plus x_(n-1)."""
    out = []
    for k in range(1, len(xs) - 2):
        out.extend(xs[k] + (xs[k + 1] - xs[k]) * i / dr.GRID for i in range(dr.GRID))
    return out + [xs[-2]]


@pytest.mark.parametrize("fn,wobs,bumps", [
    (knee30, tuple(float(w) for w in range(10, 65, 5)), {}),
    (knee30, tuple(float(w) for w in range(10, 65, 5)), {35.0: 40.0}),
    (knee26, WOBS, {16.0: 40.0, 40.0: -3.0}),
])
def test_the_kept_breakpoint_is_never_worse_than_the_best_grid_point(fn, wobs, bumps):
    data = steps(fn, wobs, bumps=bumps)
    xs, ys = [s["wob_klbf"] for s in data], [s["rop_ft_hr"] for s in data]
    best_grid = min(dr.lad_hinge(xs, ys, b)[1] for b in _grid(xs))
    assert dr.evaluate(PARAMS, data)["sum_abs_residuals"] <= best_grid


def test_the_breakpoint_keeps_two_steps_on_each_side():
    data = [{"wob_klbf": w, "rpm": 120.0, "rop_ft_hr": r} for w, r in
            ((10.0, 2.0), (15.0, 40.0), (20.0, 41.0), (25.0, 42.0), (30.0, 43.0), (35.0, 44.0), (40.0, 45.0))]
    r = dr.evaluate(PARAMS, data)
    assert 15.0 <= r["fitted_breakpoint_wob_klbf"] <= 35.0


def test_robust_scale_follows_the_stated_formula_and_ordinary_noise_is_not_flagged():
    pattern = (0.5, -0.5, 0.4, -0.3, 0.5, -0.4, 0.3, -0.5, 0.4, -0.4)
    r = dr.evaluate(PARAMS, steps(bumps={w: e for w, e in zip(WOBS, pattern)}))
    vertex = {WOBS.index(w) for w in r["vertex_wob_klbf"]}
    off = sorted(abs(x) for i, x in enumerate(r["residuals"]) if i not in vertex)
    median = off[len(off) // 2] if len(off) % 2 else 0.5 * (off[len(off) // 2 - 1] + off[len(off) // 2])
    assert len(vertex) == 3 and r["robust_scale"] == pytest.approx(1.4826 * median, rel=1e-12)
    assert r["robust_scale"] > 0.1 and r["flagged_wob_klbf"] == []
    assert max(abs(x) for x in r["residuals"]) < 3 * r["robust_scale"]


def test_linear_and_falling_data_have_no_founder():
    r = dr.evaluate(PARAMS, steps(lambda w: 3 * w + 5))
    assert r["founder_status"] == dr.NO_FOUNDER and r["breakpoint_wob_klbf"] is None
    r = dr.evaluate(PARAMS, steps(lambda w: 200 - 2 * w))
    assert r["founder_status"] == dr.NO_FOUNDER and "not positive" in r["reason"]


# ---- WOB basis (E6b): declared, never converted -----------------------------------------------------------------------
def test_wob_basis_is_declared_never_defaulted_or_converted():
    missing = dr.evaluate(dict(PARAMS, wob_basis=None), steps())
    assert missing["status"] == dr.NOT_ASSESSED and "wob_basis" in missing["reason"]
    with pytest.raises(ValueError):
        dr.evaluate(dict(PARAMS, wob_basis="hookload"), steps())
    surface = dr.evaluate(PARAMS, steps())
    downhole = dr.evaluate(dict(PARAMS, wob_basis="downhole"), steps())
    for key in ("fitted_breakpoint_wob_klbf", "slope_below", "slope_above", "intercept"):
        assert surface[key] == downhole[key]                  # the typed values are used as typed
    assert surface["inputs_sha256"] != downhole["inputs_sha256"]
    assert any("surface - not downhole WOB" in line for line in dr.summary_lines(surface))
    assert any("downhole, as declared by the user" in line for line in dr.summary_lines(downhole))
    src = inspect.getsource(dr)
    for word in ("hook_load", "hookload", "drag", "buoyan"):
        assert word not in src.split('"""')[2].lower()        # no conversion model in the code body


def test_refusals_and_bounds():
    assert dr.evaluate(PARAMS, steps(wobs=WOBS[:5]))["status"] == dr.NOT_ASSESSED
    many = steps(lambda w: 2 * w, [float(w) for w in range(1, 32)])
    assert "bounded" in dr.evaluate(PARAMS, many)["reason"]
    varied = steps()
    varied[3]["rpm"] = 140.0
    assert "not a drill-off test" in dr.evaluate(PARAMS, varied)["reason"]
    for bad_params, bad_steps in ((PARAMS, steps(wobs=(10.0, 10.0, 20.0, 25.0, 30.0, 35.0))),
                                  (dict(PARAMS, slope_ratio=1.0), steps()), (dict(PARAMS, slope_ratio=0.0), steps()),
                                  (dict(PARAMS, rpm_tolerance_rpm=-1.0), steps()),
                                  (dict(PARAMS, extra=1.0), steps()),
                                  (PARAMS, [{"wob_klbf": float("nan"), "rpm": 120.0, "rop_ft_hr": 1.0}]),
                                  (PARAMS, [{"wob_klbf": True, "rpm": 120.0, "rop_ft_hr": 1.0}]),
                                  (PARAMS, [{"wob_klbf": -1.0, "rpm": 120.0, "rop_ft_hr": 1.0}]),
                                  (PARAMS, [{"wob_klbf": 1.0, "rpm": 120.0, "rop_ft_hr": 1.0, "torque": 1}])):
        with pytest.raises(ValueError):
            dr.evaluate(bad_params, bad_steps)
    partial = steps() + [{"wob_klbf": 50.0, "rpm": None, "rop_ft_hr": 3.0}]
    assert dr.evaluate(PARAMS, partial)["steps_used"] == 10                 # incomplete step is not a step


def test_m372_and_m423_keep_their_ids_versions_and_results():
    assert mse_drilloff.METHOD_ID == "m372.mse_drilloff" and df.METHOD_ID == "m423.drilloff_fitted"
    assert df.METHOD_VERSION == "M423 drill-off founder, continuous two-segment least squares v1"
    assert len({dr.METHOD_ID, df.METHOD_ID, mse_drilloff.METHOD_ID}) == 3
    r = df.evaluate({"rpm_tolerance_rpm": 5.0, "slope_ratio": 0.5}, steps())
    assert r["breakpoint_wob_klbf"] == pytest.approx(26.0, abs=1e-6)


# ---- M476: case, replay, catalogue -----------------------------------------------------------------------------------
def test_saved_case_replays_and_tampering_is_caught(db):  # noqa: F811
    case = dr.save_case(db, dr.evaluate(PARAMS, steps(bumps={16.0: 40.0})), well_id=db.test_well_id)
    assert case["method"] == dr.METHOD_ID and hr.handles(dr.METHOD_ID)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert entry.results["wob_basis"]["value"] == "surface" and entry.results["flagged_wob_klbf"]["value"] == "16"
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    changed = copy.deepcopy(entry.results)
    changed["fitted_breakpoint_wob_klbf"]["value"] += 1.0
    out = ch.recalculate_entry(dataclasses.replace(entry, results=changed), db)
    assert out["status"] == "DIFFERENT" and [d["field_id"] for d in out["differences"]] == ["fitted_breakpoint_wob_klbf"]
    tampered = copy.deepcopy(entry.inputs)
    tampered["wob_basis"]["value"] = "downhole"
    out = ch.recalculate_entry(dataclasses.replace(entry, inputs=tampered), db)
    assert out["status"] == "UNREADABLE" and "SHA-256" in out["detail"]
    assert ch.recalculate_entry(dataclasses.replace(entry, version="v0"), db)["status"] == "NOT_REPRODUCIBLE"
    for key in changed:
        assert hr._unit_of(dr.METHOD_ID, key) in hr.FIELD_TOLERANCES
    with pytest.raises(ValueError):
        dr.save_case(db, dr.evaluate(dict(PARAMS, wob_basis=None), steps()), well_id=db.test_well_id)


def test_catalogue_lists_v2_unapproved_next_to_m423():
    from core import method_catalogue as mc

    entries = {e.method_id: e for e in mc.catalogue()}
    entry = entries[dr.METHOD_ID]
    assert entry.version == dr.METHOD_VERSION and df.METHOD_ID in entries
    assert "APPROVED" not in entry.label.replace("NOT APPROVED", "")
    assert "never converted" in entry.limits and "not a validated downhole method" in entry.limits


# ---- M477: W13 dialog (UI -> service -> case -> replay) -----------------------------------------------------------
def test_w13_robust_dialog_runs_saves_and_replays(db):  # noqa: F811
    from PySide6 import QtWidgets
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = EngineeringCalculatorTab(db)
    dialog = None
    try:
        tab.on_well_changed(db.test_well_id, {"name": "SYN-C-01"})
        assert tab.drilloff_robust_btn.objectName() == "drilloff_robust_btn"
        tab.bit_wob.setValue(8.0)
        tab.bit_rpm.setValue(120.0)
        tab.bit_rop.setValue(32.0)
        dialog = tab.drilloff_robust_dialog()
        assert [dialog.table.item(0, c).text() for c in range(3)] == ["8", "120", "32"]
        assert dialog.combos["wob_basis"].currentData() is None                  # the basis is never preset
        dialog.set_value("rpm_tolerance_rpm", 5.0)
        dialog.set_value("slope_ratio", 0.5)
        for row, step in enumerate(steps(bumps={16.0: 40.0})):
            dialog.set_row(row, step)
        first = dialog.run()
        assert first["status"] == dr.NOT_ASSESSED and not dialog.save_btn.isEnabled()
        dialog.set_value("wob_basis", "surface")
        result = dialog.run()
        assert result["breakpoint_wob_klbf"] == pytest.approx(26.0, abs=1e-6)
        assert "surface - not downhole WOB" in dialog.summary.text()
        case = dialog.save()
        entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
        assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    finally:
        if dialog is not None:
            dialog.deleteLater()
        tab.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


# ---- M482: Erge 2015 is reported NOT VERIFIED; numbers and replay unchanged ----------------------------------------
HB = {"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 10000.0, "flow_rate_gpm": 300.0, "density_ppg": 10.0,
      "tau0_lbf_100ft2": 8.0, "k_lbf_sn_100ft2": 1.2, "n_index": 0.6, "roughness_in": 0.0018}


def test_erge_is_marked_not_verified_everywhere_it_is_shown(db):  # noqa: F811
    erge = hb.evaluate(dict(HB, transition_criterion="erge-2015"))
    fk = hb.evaluate(dict(HB, transition_criterion="founargiotakis-2008"))
    assert erge["status"] == fk["status"] == hb.COMPUTED
    assert "NOT VERIFIED" in erge["verification_note"] and fk["verification_note"] is None
    assert any(line.startswith("NOT VERIFIED:") for line in hb.summary_lines(erge))
    assert not any("NOT VERIFIED" in line for line in hb.summary_lines(fk))
    refused = hb.evaluate(dict(HB, n_index=0.3, transition_criterion="erge-2015", flow_rate_gpm=700.0))
    assert refused["status"] == hb.NOT_ASSESSED and any("NOT VERIFIED" in x for x in hb.summary_lines(refused))
    assert "verification_note" not in str(hb.case_payload(erge))                 # not a replayed result
    case = hb.save_case(db, erge, well_id=db.test_well_id)
    entry = next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"])
    assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
    from core import calculation_cases as cc

    assert "NOT VERIFIED" in (cc.get_case(db, case["id"]).get("note") or "")
    surge = {"trip_speed_ft_min": 60.0, "clinging_constant": 0.5, "density_ppg": 10.0, "tau0_lbf_100ft2": 8.0,
             "k_lbf_sn_100ft2": 1.2, "n_index": 0.6, "roughness_in": 0.0018, "tvd_ft": 10000.0,
             "transition_criterion": "erge-2015", "pipe_end": "closed"}
    sections = [{"hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 5000.0}]
    assert any("NOT VERIFIED" in line for line in ss.summary_lines(ss.evaluate(surge, sections)))
    assert hb.verification_note("founargiotakis-2008") is None and hb.verification_note(None) is None
