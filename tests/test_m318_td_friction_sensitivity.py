"""M318 (M281): friction-factor sensitivity on one pinned T&D run (SYNTHETIC, SCREENING).

Independent anchors: vertical 10,000 ft of 19.5 ppf in 10 ppg mud has a buoyed weight of 165.23 klbf
(BF = 1 − 10/65.5), and with FF 0 pickup, slack-off and rotating hookloads coincide. In a deviated well pickup
and torque rise with FF while slack-off falls.
"""
from __future__ import annotations

import pytest

from core import calculation_cases as cc
from core import torque_drag_sensitivity as tds

PIPE = [{"name": "SYN DP", "od": 5.0, "id": 4.276, "length": 3048.0, "weight": 19.5}]
VERTICAL = [{"md": 0, "inc": 0, "azi": 0}, {"md": 3048.0, "inc": 0, "azi": 0}]
DEVIATED = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}, {"md": 1500, "inc": 45, "azi": 30},
            {"md": 3048, "inc": 60, "azi": 40}]


def _run(survey, **extra):
    from core.survey_revisions import stations_sha256
    from core.w13_weight import engine_components

    pin = {"revision_id": 7, "revision": 2, "stations_sha256": stations_sha256(survey)}
    return {"survey": survey, "components": engine_components(PIPE), "mud_density_ppg": 10.0, "wob_klbf": 0.0,
            "wellbore_id_in": None, "survey_source": pin, **extra}


def test_vertical_anchor_and_ff_zero_identity():
    result = tds.sweep(_run(VERTICAL), [0.0, 0.3])
    first = result["rows"][0]
    assert first["pickup"] == pytest.approx(165.23, abs=0.05)
    assert first["pickup"] == pytest.approx(first["slackoff"]) == pytest.approx(first["rotating"])
    assert result["rows"][1]["pickup"] == pytest.approx(165.23, abs=0.05)   # vertical: no normal force
    assert tds.locate(result, "rotating", 165.0)["status"] == tds.NOT_CHECKED  # flat curve: never located


def test_deviated_curves_are_monotonic_in_the_expected_direction():
    result = tds.sweep(_run(DEVIATED), [0.4, 0.1, 0.2, 0.3, 0.2])
    assert result["factors"] == [0.1, 0.2, 0.3, 0.4]                         # sorted, duplicate removed
    pickup = [r["pickup"] for r in result["rows"]]
    slack = [r["slackoff"] for r in result["rows"]]
    torque = [r["torque"] for r in result["rows"]]
    assert pickup == sorted(pickup) and pickup[0] < pickup[-1]
    assert slack == sorted(slack, reverse=True) and slack[0] > slack[-1]
    assert torque == sorted(torque) and torque[0] < torque[-1]
    assert result["label"] == tds.LABEL and result["failed"] == []


def test_locate_brackets_but_never_interpolates_a_friction_factor():
    result = tds.sweep(_run(DEVIATED), [0.1, 0.2, 0.3, 0.4])
    rows = result["rows"]
    middle = (rows[1]["torque"] + rows[2]["torque"]) / 2
    where = tds.locate(result, "torque", middle)
    assert where["status"] == tds.BETWEEN and where["friction_factors"] == [0.2, 0.3]
    assert "apparent" not in where["reason"] and "friction_factor" not in where
    assert tds.locate(result, "torque", rows[2]["torque"])["status"] == tds.AT
    assert tds.locate(result, "pickup", rows[0]["pickup"] - 50)["status"] == tds.BELOW
    assert tds.locate(result, "slackoff", rows[0]["slackoff"] + 50)["status"] == tds.ABOVE
    slack_mid = (rows[0]["slackoff"] + rows[1]["slackoff"]) / 2                # falling curve
    assert tds.locate(result, "slackoff", slack_mid)["friction_factors"] == [0.1, 0.2]
    assert tds.locate(result, "pickup", None)["status"] == tds.NOT_CHECKED
    with pytest.raises(tds.SensitivityError):
        tds.locate(result, "stretch", 1.0)


def test_one_factor_cannot_be_located():
    result = tds.sweep(_run(DEVIATED), [0.25])
    assert tds.locate(result, "torque", 1000.0)["status"] == tds.NOT_CHECKED


@pytest.mark.parametrize("text, message", [
    ("", "no default"), ("0,25 0,3", "commas are refused"), ("0.2 abc", "not a number"),
    ("0.2 1.5", "outside [0, 1]"), ("-0.1", "outside [0, 1]"),
    (" ".join(f"{i / 100:.2f}" for i in range(13)), "At most 12"),
])
def test_declared_factors_are_validated(text, message):
    with pytest.raises(tds.SensitivityError, match=message.replace("[", r"\[").replace("]", r"\]")):
        tds.parse_factors(text)


def test_parse_accepts_spaces_and_semicolons():
    assert tds.parse_factors("0.3; 0.1  0.2;0.1") == [0.1, 0.2, 0.3]
    with pytest.raises(tds.SensitivityError):
        tds.normalize_factors([True])
    with pytest.raises(tds.SensitivityError):
        tds.normalize_factors([float("nan")])


def test_no_run_is_refused_and_an_engine_refusal_is_listed_not_skipped():
    with pytest.raises(tds.SensitivityError, match="pinned survey"):
        tds.sweep(None, [0.2])
    broken = _run(DEVIATED, mud_density_ppg=-1.0)
    result = tds.sweep(broken, [0.1, 0.2])
    assert result["failed"] == [0.1, 0.2] and all(r["pickup"] is None for r in result["rows"])
    assert all(r["reason"] for r in result["rows"])
    assert "FAILED" in tds.table_lines(result)[2]


def test_save_stores_declared_factors_observations_and_locations(tmp_path):
    from synthetic_operations import build_synthetic_operations, make_file_database

    db = make_file_database(tmp_path / "m318.db")
    try:
        ids = build_synthetic_operations(db)
        result = tds.sweep(_run(DEVIATED), [0.1, 0.3])
        observed = {"torque": (result["rows"][0]["torque"] + result["rows"][1]["torque"]) / 2, "pickup": None}
        case = tds.save_case(db, result, observed, well_id=ids["dev"])
        stored = cc.get_case(db, case["id"])
        assert stored["inputs"]["friction_factors"]["value"] == [0.1, 0.3]
        assert stored["inputs"]["observed_pickup"]["source"] == "NOT_ENTERED"
        assert stored["results"]["located_torque"]["value"] == tds.BETWEEN
        assert stored["results"]["located_pickup"]["value"] == tds.NOT_CHECKED
        assert stored["method_version"] == tds.METHOD_VERSION and tds.LABEL in stored["note"]
        from core import calculation_history as ch
        entry = [e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case["id"]][0]
        assert ch.entry_status(entry)["reproducible"] == "REPRODUCIBLE"       # M328 replay adapter
        assert ch.recalculate_entry(entry, db)["status"] == "MATCH"
        with pytest.raises(ValueError):
            tds.save_case(db, tds.sweep(_run(DEVIATED, mud_density_ppg=-1.0), [0.1]), {}, well_id=ids["dev"])
    finally:
        db.engine.dispose()


# ---- UI: W13 › Weight › "Friction-factor sensitivity" (the production path after a pinned T&D run) -------------
from tests.test_m127_weight_casing import SLANT, _choose, _fill_weight, app, env, w13  # noqa: E402,F401,F811


def test_w13_sensitivity_runs_on_the_last_pinned_run_and_saves(w13, env):  # noqa: F811
    from core import survey_revisions as sr

    manager, ids = env
    w13.wt_ff_list.setText("0.2 0.3")
    w13.wt_ff_run_btn.click()                                        # no T&D run yet
    assert w13.wt_ff_result.text().startswith("NOT RUN") and not w13.wt_ff_save_btn.isEnabled()
    rev = sr.save_revision(manager, ids["A"][0], SLANT, depth_datum="RKB", azimuth_reference="true")
    _fill_weight(w13)
    w13._wt_reload_survey_revisions()
    _choose(w13, rev["id"])
    w13._wt_calculate()
    assert w13._wt_last_td_run is not None
    w13.wt_ff_list.setText("")
    w13.wt_ff_run_btn.click()
    assert "no default" in w13.wt_ff_result.text()
    w13.wt_ff_list.setText("0,2 0,3")
    w13.wt_ff_run_btn.click()
    assert "commas are refused" in w13.wt_ff_result.text()
    w13.wt_ff_list.setText("0.1 0.2 0.3")
    result = w13.run_ff_sensitivity()
    torque = [r["torque"] for r in result["rows"]]
    w13.wt_ff_observed["torque"].setText(f"{(torque[0] + torque[1]) / 2:.3f}")
    w13.wt_ff_observed["pickup"].setText("1,5")
    w13.wt_ff_run_btn.click()
    text = w13.wt_ff_result.text()
    assert tds.LABEL in text and "Observed torque: BETWEEN" in text and "pickup: '1,5': commas are refused" in text
    assert w13.wt_ff_save_btn.isEnabled()
    w13.wt_ff_save_btn.click()
    assert "Saved as calculation case" in w13.wt_ff_result.text() and not w13.wt_ff_save_btn.isEnabled()
    case = cc.list_cases(manager, calculator="T&D friction sensitivity", well_id=ids["A"][0])[0]
    assert case["inputs"]["survey_revision_id"]["value"] == rev["id"]
    assert case["inputs"]["observed_pickup"]["value"] is None             # the refused observation is not stored


# ---- M327: locate() rules on hand-built curves (mutation survivors) ----------------------------------------------
def _curve(values, curve="torque"):
    return {"rows": [{"friction_factor": 0.1 * (i + 1), "status": "OK", curve: v} for i, v in enumerate(values)]}


def test_a_non_monotonic_curve_is_never_located():
    where = tds.locate(_curve([100.0, 300.0, 200.0]), "torque", 250.0)
    assert where["status"] == tds.NOT_CHECKED and "not monotonic" in where["reason"]


def test_one_factor_states_why_it_cannot_be_located():
    where = tds.locate(_curve([100.0]), "torque", 100.0)
    assert where["status"] == tds.NOT_CHECKED and where["reason"] == "fewer than two successful friction factors"


def test_an_observed_zero_is_an_observation():
    where = tds.locate(_curve([100.0, 200.0]), "torque", 0.0)
    assert where["status"] == tds.BELOW and "observed 0" in where["reason"]
